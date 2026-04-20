#!/usr/bin/env bash
# =============================================================================
#  MTProto Proxy + Webhook Bridge — Installation Wizard
#  Поддерживается: Ubuntu 22.04 / 24.04
#
#  Использование:
#    ./install.sh                     — обычная установка (пропускает готовые шаги)
#    ./install.sh --force             — полная переустановка всех шагов
#    ./install.sh --force-step=env    — перезапустить только конкретный шаг
#
#  Шаги: packages | docker | env | firewall | launch
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_FILE="$SCRIPT_DIR/.install-state"
LOG_FILE="$SCRIPT_DIR/.install.log"
ENV_FILE="$SCRIPT_DIR/.env"

FORCE=false
FORCE_STEP=""

for arg in "$@"; do
    case "$arg" in
        --force)            FORCE=true ;;
        --force-step=*)     FORCE_STEP="${arg#*=}" ;;
        --help|-h)
            sed -n '2,10p' "$0" | sed 's/^# \?//'
            exit 0 ;;
    esac
done

# ── Цвета ─────────────────────────────────────────────────────────────────────
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_CYAN='\033[0;36m'
C_GRAY='\033[0;90m'

log()      { echo -e "${C_GRAY}[$(date '+%H:%M:%S')]${C_RESET} $*" | tee -a "$LOG_FILE"; }
info()     { echo -e "${C_CYAN}${C_BOLD}  →${C_RESET} $*" | tee -a "$LOG_FILE"; }
success()  { echo -e "${C_GREEN}${C_BOLD}  ✓${C_RESET} $*" | tee -a "$LOG_FILE"; }
warn()     { echo -e "${C_YELLOW}${C_BOLD}  ⚠${C_RESET} $*" | tee -a "$LOG_FILE"; }
error()    { echo -e "${C_RED}${C_BOLD}  ✗${C_RESET} $*" | tee -a "$LOG_FILE" >&2; }
die()      { error "$*"; exit 1; }

header() {
    echo ""
    echo -e "${C_BOLD}${C_CYAN}══════════════════════════════════════════${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}  $*${C_RESET}"
    echo -e "${C_BOLD}${C_CYAN}══════════════════════════════════════════${C_RESET}"
    echo ""
}

step_header() {
    echo ""
    echo -e "${C_BOLD}┌─ $* ${C_RESET}"
}

# ── State management ──────────────────────────────────────────────────────────
state_get() {
    local key="$1"
    if [[ -f "$STATE_FILE" ]]; then
        grep -m1 "^${key}=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || true
    fi
}

state_set() {
    local key="$1" val="$2"
    if [[ -f "$STATE_FILE" ]] && grep -q "^${key}=" "$STATE_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$STATE_FILE"
    else
        echo "${key}=${val}" >> "$STATE_FILE"
    fi
}

step_done() {
    local step="$1"
    [[ "$FORCE" == true ]] && return 1
    [[ "$FORCE_STEP" == "$step" ]] && return 1
    [[ "$(state_get "STEP_${step^^}")" == "done" ]]
}

mark_done() {
    state_set "STEP_${1^^}" "done"
    success "Шаг '${1}' завершён и записан."
}

# ── Ввод данных ───────────────────────────────────────────────────────────────
ask() {
    # ask <var_name> <prompt> [default]
    local var="$1" prompt="$2" default="${3:-}"
    local hint=""
    [[ -n "$default" ]] && hint=" ${C_GRAY}[${default}]${C_RESET}"
    echo -ne "${C_BOLD}  ${prompt}${hint}: ${C_RESET}"
    local val
    read -r val
    val="${val:-$default}"
    while [[ -z "$val" ]]; do
        echo -ne "  ${C_RED}Обязательное поле.${C_RESET} ${prompt}: "
        read -r val
    done
    printf -v "$var" '%s' "$val"
}

ask_optional() {
    local var="$1" prompt="$2" default="${3:-}"
    local hint=" ${C_GRAY}[Enter — пропустить]${C_RESET}"
    [[ -n "$default" ]] && hint=" ${C_GRAY}[${default}]${C_RESET}"
    echo -ne "${C_BOLD}  ${prompt}${hint}: ${C_RESET}"
    local val
    read -r val
    val="${val:-$default}"
    printf -v "$var" '%s' "$val"
}

ask_secret() {
    local var="$1" prompt="$2"
    local val confirm
    while true; do
        echo -ne "${C_BOLD}  ${prompt}: ${C_RESET}"
        read -rs val; echo ""
        echo -ne "${C_BOLD}  Повтори: ${C_RESET}"
        read -rs confirm; echo ""
        if [[ "$val" == "$confirm" ]]; then
            break
        fi
        warn "Значения не совпадают, попробуй снова."
    done
    printf -v "$var" '%s' "$val"
}

ask_yes_no() {
    local prompt="$1" default="${2:-y}"
    local hint="[Y/n]"
    [[ "$default" == "n" ]] && hint="[y/N]"
    echo -ne "${C_BOLD}  ${prompt} ${C_GRAY}${hint}${C_RESET}: "
    local val
    read -r val
    val="${val:-$default}"
    [[ "${val,,}" == "y" || "${val,,}" == "yes" ]]
}

# Читает многострочный PEM-блок, конвертирует в \n-escaped строку для .env
ask_pem() {
    local var="$1" label="$2"
    echo -e "  ${C_BOLD}${label}${C_RESET}"
    echo -e "  ${C_GRAY}Вставь весь блок (от -----BEGIN до -----END...), затем Enter + Ctrl+D${C_RESET}"
    echo ""
    local lines=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        lines+=("$line")
        [[ "$line" == -----END* ]] && break
    done
    if [[ ${#lines[@]} -lt 3 ]]; then
        die "PEM-блок слишком короткий. Вставь содержимое файла целиком."
    fi
    # Склеиваем строки через \n для хранения в .env (одна строка)
    local result
    result="$(printf '%s\n' "${lines[@]}" | awk '{printf "%s\\n", $0}' | sed 's/\\n$//')"
    printf -v "$var" '%s' "$result"
}

# ── APT с fallback'ами ────────────────────────────────────────────────────────
apt_update_with_retry() {
    local attempts=3
    local wait=5

    for i in $(seq 1 $attempts); do
        info "apt update (попытка ${i}/${attempts})..."
        if sudo apt-get update -qq >> "$LOG_FILE" 2>&1; then
            success "apt update успешен."
            return 0
        fi
        warn "apt update не удался, жду ${wait}с..."
        sleep "$wait"
        wait=$((wait * 2))
    done

    # Fallback: попробуем со сменой DNS
    warn "Пробую с резолвером 8.8.8.8..."
    echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf.bak > /dev/null
    if sudo apt-get update -qq >> "$LOG_FILE" 2>&1; then
        success "apt update через 8.8.8.8 успешен."
        return 0
    fi

    # Fallback: --fix-missing
    warn "Пробую apt update --fix-missing..."
    if sudo apt-get update --fix-missing -qq >> "$LOG_FILE" 2>&1; then
        success "apt update --fix-missing успешен."
        return 0
    fi

    die "apt update провалился после всех попыток. Проверь подключение к интернету и логи: $LOG_FILE"
}

apt_install_with_retry() {
    local packages=("$@")
    local to_install=()

    # Устанавливаем только то, чего ещё нет
    for pkg in "${packages[@]}"; do
        if dpkg -s "$pkg" &>/dev/null; then
            log "  $pkg — уже установлен"
        else
            to_install+=("$pkg")
        fi
    done

    if [[ ${#to_install[@]} -eq 0 ]]; then
        success "Все пакеты уже установлены."
        return 0
    fi

    info "Устанавливаю: ${to_install[*]}"
    local attempts=3
    for i in $(seq 1 $attempts); do
        if sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${to_install[@]}" >> "$LOG_FILE" 2>&1; then
            success "Пакеты установлены."
            return 0
        fi
        warn "Установка не удалась (попытка ${i}/${attempts}), жду 5с..."
        sleep 5
    done

    # Fallback: по одному
    warn "Пробую устанавливать пакеты по одному..."
    local failed=()
    for pkg in "${to_install[@]}"; do
        if ! sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg" >> "$LOG_FILE" 2>&1; then
            failed+=("$pkg")
            warn "  Не удалось установить: $pkg"
        fi
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        die "Не удалось установить: ${failed[*]}. Смотри лог: $LOG_FILE"
    fi
    success "Все пакеты установлены (по одному)."
}

# ── Определить docker compose команду ─────────────────────────────────────────
detect_compose() {
    if docker compose version &>/dev/null 2>&1; then
        echo "docker compose"
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose"
    else
        echo ""
    fi
}

# ── ШАГИ УСТАНОВКИ ───────────────────────────────────────────────────────────

# ── Шаг 0: Preflight ─────────────────────────────────────────────────────────
step_preflight() {
    step_header "Preflight checks"

    # OS
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        if [[ "$ID" != "ubuntu" ]]; then
            warn "Обнаружена ОС: ${PRETTY_NAME}. Скрипт тестировался на Ubuntu 22.04/24.04."
            ask_yes_no "Продолжить на неподдерживаемой ОС?" "n" || die "Установка отменена."
        else
            success "ОС: ${PRETTY_NAME}"
        fi
    fi

    # sudo
    if [[ "$EUID" -eq 0 ]]; then
        warn "Запущен от root. Рекомендуется запускать от обычного пользователя с sudo."
    else
        if ! sudo -n true 2>/dev/null; then
            info "Для установки нужны права sudo. Введи пароль:"
            sudo true || die "Не удалось получить sudo."
        fi
        success "sudo доступен."
    fi

    # Уже установлено?
    if [[ -f "$ENV_FILE" ]] && [[ "$FORCE" == false ]] && [[ "$FORCE_STEP" != "env" ]]; then
        warn ".env уже существует."
        if ! ask_yes_no "Файл .env уже есть. Хочешь перенастроить?" "n"; then
            info "Используется существующий .env."
        fi
    fi

    success "Preflight пройден."
}

# ── Шаг 1: Системные пакеты ──────────────────────────────────────────────────
step_packages() {
    step_done "packages" && { success "Шаг 'packages' — уже выполнен. (--force-step=packages для повтора)"; return 0; }
    step_header "Системные пакеты"

    apt_update_with_retry
    apt_install_with_retry \
        curl wget git ca-certificates gnupg lsb-release \
        apt-transport-https software-properties-common \
        ufw net-tools

    mark_done "packages"
}

# ── Шаг 2: Docker + Compose ──────────────────────────────────────────────────
step_docker() {
    step_done "docker" && { success "Шаг 'docker' — уже выполнен. (--force-step=docker для повтора)"; return 0; }
    step_header "Docker + Docker Compose"

    # Docker Engine
    if command -v docker &>/dev/null; then
        local ver
        ver=$(docker --version 2>/dev/null || true)
        success "Docker уже установлен: ${ver}"
    else
        info "Устанавливаю Docker..."

        # Попытка 1: официальный скрипт
        if curl -fsSL https://get.docker.com -o /tmp/get-docker.sh >> "$LOG_FILE" 2>&1; then
            if sudo sh /tmp/get-docker.sh >> "$LOG_FILE" 2>&1; then
                success "Docker установлен через get.docker.com"
            else
                warn "Официальный скрипт не сработал, пробую вручную через apt..."
                _docker_install_apt
            fi
        else
            warn "Не удалось скачать get.docker.com, пробую через apt..."
            _docker_install_apt
        fi
    fi

    # Добавить текущего пользователя в группу docker
    if [[ "$EUID" -ne 0 ]]; then
        if ! groups "$USER" | grep -q docker; then
            sudo usermod -aG docker "$USER"
            warn "Пользователь ${USER} добавлен в группу docker. Изменения вступят в силу после re-login."
            warn "В этом сеансе команды docker будут запускаться через sudo."
        fi
    fi

    # Запустить и включить docker
    sudo systemctl enable docker >> "$LOG_FILE" 2>&1 || true
    sudo systemctl start  docker >> "$LOG_FILE" 2>&1 || true

    # Docker Compose
    local compose_cmd
    compose_cmd=$(detect_compose)

    if [[ -n "$compose_cmd" ]]; then
        local cv
        cv=$($compose_cmd version 2>/dev/null || true)
        success "Docker Compose: ${cv} (команда: '${compose_cmd}')"
    else
        info "Docker Compose не найден, устанавливаю плагин..."

        if sudo apt-get install -y -qq docker-compose-plugin >> "$LOG_FILE" 2>&1; then
            success "docker-compose-plugin установлен."
        else
            # Fallback: standalone docker-compose v2
            warn "Плагин недоступен, ставлю standalone docker-compose..."
            local compose_url="https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)"
            if sudo curl -fsSL "$compose_url" -o /usr/local/bin/docker-compose >> "$LOG_FILE" 2>&1; then
                sudo chmod +x /usr/local/bin/docker-compose
                success "standalone docker-compose установлен в /usr/local/bin/"
            else
                die "Не удалось установить Docker Compose. Установи вручную: https://docs.docker.com/compose/install/"
            fi
        fi
    fi

    # Финальная проверка
    compose_cmd=$(detect_compose)
    [[ -z "$compose_cmd" ]] && die "Docker Compose недоступен после установки."
    state_set "COMPOSE_CMD" "$compose_cmd"

    mark_done "docker"
}

_docker_install_apt() {
    info "Установка Docker через официальный репозиторий apt..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg >> "$LOG_FILE" 2>&1
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt_update_with_retry
    apt_install_with_retry docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

# ── Шаг 3: Конфигурация .env ─────────────────────────────────────────────────
step_env() {
    step_done "env" && { success "Шаг 'env' — уже выполнен. (--force-step=env для повтора)"; return 0; }
    step_header "Настройка конфигурации (.env)"

    echo ""
    echo -e "  Буду задавать вопросы для заполнения файла ${C_BOLD}.env${C_RESET}."
    echo -e "  Значения в ${C_GRAY}[скобках]${C_RESET} — дефолтные, просто нажми Enter."
    echo ""

    # ── Сервер ────────────────────────────────────────────────────────────────
    echo -e "  ${C_BOLD}─── Сервер ───────────────────────────────────────${C_RESET}"

    local auto_ip
    auto_ip=$(curl -sf --max-time 5 https://api.ipify.org 2>/dev/null \
        || curl -sf --max-time 5 https://ifconfig.me 2>/dev/null \
        || curl -sf --max-time 5 https://icanhazip.com 2>/dev/null \
        || hostname -I | awk '{print $1}' || true)

    local PROXY_HOST PROXY_PORT
    ask PROXY_HOST "Публичный IP / домен VPS" "${auto_ip}"
    ask PROXY_PORT "Порт MTProto прокси" "2083"

    # ── Redis ─────────────────────────────────────────────────────────────────
    echo ""
    echo -e "  ${C_BOLD}─── Redis ────────────────────────────────────────${C_RESET}"
    local REDIS_PASSWORD
    local auto_redis_pass
    auto_redis_pass=$(openssl rand -hex 20 2>/dev/null || tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32)
    ask REDIS_PASSWORD "Пароль Redis (или Enter для авто)" "${auto_redis_pass}"

    # ── HTTP API ──────────────────────────────────────────────────────────────
    echo ""
    echo -e "  ${C_BOLD}─── HTTP API ─────────────────────────────────────${C_RESET}"
    local API_KEY API_PORT
    local auto_api_key
    auto_api_key=$(openssl rand -hex 24 2>/dev/null || tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 48)
    ask API_KEY "API ключ (X-Api-Key)" "${auto_api_key}"
    ask API_PORT "Порт HTTP API" "8080"

    # ── MTProxy ───────────────────────────────────────────────────────────────
    echo ""
    echo -e "  ${C_BOLD}─── MTProto прокси ───────────────────────────────${C_RESET}"

    local TLS_DOMAIN AD_TAG
    ask TLS_DOMAIN "Fake-TLS домен (маскировка трафика под HTTPS)" "www.google.com"

    echo -e "  ${C_GRAY}AD_TAG — hex-тег рекламного канала от @MTProxybot. Оставь пустым если не нужно.${C_RESET}"
    ask_optional AD_TAG "AD_TAG" ""

    # ── Cloudflare Origin Certificate ─────────────────────────────────────────
    echo ""
    echo -e "  ${C_BOLD}─── Cloudflare Origin Certificate ───────────────${C_RESET}"
    echo -e "  ${C_GRAY}Cloudflare Dashboard → SSL/TLS → Origin Server → Create Certificate${C_RESET}"
    echo -e "  ${C_GRAY}Выбери срок действия 15 лет, тип RSA, скопируй оба блока.${C_RESET}"
    echo ""

    local CF_ORIGIN_CERT CF_ORIGIN_KEY
    ask_pem CF_ORIGIN_CERT "Origin Certificate (origin.pem / Certificate):"
    echo ""
    ask_pem CF_ORIGIN_KEY "Private Key (origin.key / Private key):"

    # ── Telegram бот (опционально) ────────────────────────────────────────────
    echo ""
    echo -e "  ${C_BOLD}─── Telegram бот (опционально) ───────────────────${C_RESET}"
    echo -e "  ${C_GRAY}Если задать BOT_TOKEN — запустится Telegram бот для управления доступами.${C_RESET}"
    echo -e "  ${C_GRAY}Если не нужен — просто нажимай Enter.${C_RESET}"
    echo ""

    local BOT_TOKEN="" ADMIN_IDS=""
    ask_optional BOT_TOKEN "BOT_TOKEN (от @BotFather)" ""

    if [[ -n "$BOT_TOKEN" ]]; then
        local my_id
        my_id=$(curl -sf --max-time 5 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" \
            | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*' 2>/dev/null || true)
        [[ -n "$my_id" ]] && info "Бот найден, ID: ${my_id}"
        ask ADMIN_IDS "ADMIN_IDS (через запятую, например: 123456789,987654321)" ""
    fi

    # ── Записываем .env ───────────────────────────────────────────────────────
    echo ""
    info "Записываю .env..."

    cat > "$ENV_FILE" <<EOF
# Сгенерировано install.sh $(date '+%Y-%m-%d %H:%M:%S')

PROXY_HOST=${PROXY_HOST}
PROXY_PORT=${PROXY_PORT}

REDIS_PASSWORD=${REDIS_PASSWORD}

API_KEY=${API_KEY}
API_PORT=${API_PORT}

TLS_DOMAIN=${TLS_DOMAIN}
AD_TAG=${AD_TAG}

CF_ORIGIN_CERT=${CF_ORIGIN_CERT}
CF_ORIGIN_KEY=${CF_ORIGIN_KEY}
EOF

    if [[ -n "$BOT_TOKEN" ]]; then
        cat >> "$ENV_FILE" <<EOF

BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}
EOF
    fi

    chmod 600 "$ENV_FILE"
    success ".env записан (права 600)."

    # Показываем итог (без секретов)
    echo ""
    echo -e "  ${C_BOLD}Итог конфигурации:${C_RESET}"
    echo -e "  PROXY_HOST    = ${C_CYAN}${PROXY_HOST}${C_RESET}"
    echo -e "  PROXY_PORT    = ${C_CYAN}${PROXY_PORT}${C_RESET} (MTProto)"
    echo -e "  API_PORT      = ${C_CYAN}${API_PORT}${C_RESET} (HTTP API)"
    echo -e "  TLS_DOMAIN    = ${C_CYAN}${TLS_DOMAIN}${C_RESET}"
    echo -e "  AD_TAG        = ${C_CYAN}${AD_TAG:-—}${C_RESET}"
    echo -e "  Telegram бот  = ${C_CYAN}${BOT_TOKEN:+включён}${BOT_TOKEN:-выключен}${C_RESET}"

    mark_done "env"
}

# ── Шаг 4: Файрвол ───────────────────────────────────────────────────────────
step_firewall() {
    step_done "firewall" && { success "Шаг 'firewall' — уже выполнен. (--force-step=firewall для повтора)"; return 0; }
    step_header "Настройка файрвола (ufw)"

    if ! command -v ufw &>/dev/null; then
        warn "ufw не найден, пропускаю."
        mark_done "firewall"
        return 0
    fi

    local ufw_status
    ufw_status=$(sudo ufw status 2>/dev/null | head -1 || true)

    local API_PORT PROXY_PORT
    API_PORT=$(grep -m1 '^API_PORT=' "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo "8080")
    PROXY_PORT=$(grep -m1 '^PROXY_PORT=' "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo "2083")

    # SSH — не трогаем если уже разрешён
    if ! sudo ufw status | grep -qE "^22|^OpenSSH"; then
        warn "Разрешаю SSH (порт 22) чтобы не потерять доступ..."
        sudo ufw allow 22/tcp >> "$LOG_FILE" 2>&1
    fi

    sudo ufw allow 443/tcp   comment "nginx webhook proxy"  >> "$LOG_FILE" 2>&1
    sudo ufw allow "${PROXY_PORT}/tcp" comment "MTProto proxy" >> "$LOG_FILE" 2>&1

    if ask_yes_no "Открыть порт ${API_PORT} (HTTP API) снаружи?" "n"; then
        sudo ufw allow "${API_PORT}/tcp" comment "MTProxy HTTP API" >> "$LOG_FILE" 2>&1
        success "Порт ${API_PORT} открыт."
    else
        info "Порт ${API_PORT} оставлен закрытым (доступен только локально)."
    fi

    if [[ "$ufw_status" == *"inactive"* ]]; then
        if ask_yes_no "ufw неактивен. Включить?" "y"; then
            sudo ufw --force enable >> "$LOG_FILE" 2>&1
            success "ufw включён."
        fi
    else
        success "ufw активен, правила добавлены."
    fi

    mark_done "firewall"
}

# ── Шаг 5: Сборка и запуск ───────────────────────────────────────────────────
step_launch() {
    step_done "launch" && {
        success "Шаг 'launch' — уже выполнен."
        if ask_yes_no "Хочешь перезапустить контейнеры?" "n"; then
            : # продолжим
        else
            return 0
        fi
    }
    step_header "Сборка и запуск контейнеров"

    local compose_cmd
    compose_cmd=$(state_get "COMPOSE_CMD")
    [[ -z "$compose_cmd" ]] && compose_cmd=$(detect_compose)
    [[ -z "$compose_cmd" ]] && die "Docker Compose не найден. Запусти шаг docker заново."

    cd "$SCRIPT_DIR"

    info "Сборка образов (это может занять пару минут)..."
    if ! sudo $compose_cmd build >> "$LOG_FILE" 2>&1; then
        die "docker compose build провалился. Смотри лог: $LOG_FILE"
    fi
    success "Образы собраны."

    info "Запуск контейнеров..."
    if ! sudo $compose_cmd up -d >> "$LOG_FILE" 2>&1; then
        die "docker compose up провалился. Смотри лог: $LOG_FILE"
    fi
    success "Контейнеры запущены."

    mark_done "launch"
}

# ── Шаг 6: Проверка ──────────────────────────────────────────────────────────
step_verify() {
    step_header "Проверка"

    local compose_cmd
    compose_cmd=$(state_get "COMPOSE_CMD")
    [[ -z "$compose_cmd" ]] && compose_cmd=$(detect_compose)

    sleep 5  # дать контейнерам подняться

    cd "$SCRIPT_DIR"
    local statuses
    statuses=$(sudo $compose_cmd ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || \
               sudo $compose_cmd ps 2>/dev/null || true)
    echo ""
    echo "$statuses"
    echo ""

    # Healthcheck HTTP API
    local API_PORT API_KEY
    API_PORT=$(grep -m1 '^API_PORT=' "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo "8080")
    API_KEY=$(grep -m1 '^API_KEY=' "$ENV_FILE" | cut -d= -f2 | tr -d '"' || true)

    info "Проверяю HTTP API..."
    local http_code
    http_code=$(curl -sf --max-time 5 -o /dev/null -w "%{http_code}" \
        "http://127.0.0.1:${API_PORT}/health" 2>/dev/null || echo "000")

    if [[ "$http_code" == "200" ]]; then
        success "HTTP API отвечает на :${API_PORT}/health"
    else
        warn "HTTP API не отвечает (код: ${http_code}). Проверь: sudo docker logs access-bot"
    fi
}

# ── Итоговый вывод ────────────────────────────────────────────────────────────
show_summary() {
    local PROXY_HOST PROXY_PORT API_PORT API_KEY
    PROXY_HOST=$(grep -m1 '^PROXY_HOST=' "$ENV_FILE" | cut -d= -f2 | tr -d '"' || echo "?")
    PROXY_PORT=$(grep -m1 '^PROXY_PORT=' "$ENV_FILE"  | cut -d= -f2 | tr -d '"' || echo "2083")
    API_PORT=$(grep -m1 '^API_PORT='   "$ENV_FILE"    | cut -d= -f2 | tr -d '"' || echo "8080")
    API_KEY=$(grep -m1 '^API_KEY='     "$ENV_FILE"    | cut -d= -f2 | tr -d '"' || echo "?")

    header "Установка завершена!"

    echo -e "  ${C_BOLD}MTProto прокси:${C_RESET}"
    echo -e "    Порт:      ${C_CYAN}${PROXY_PORT}${C_RESET}"
    echo -e "    Ссылка:    ${C_CYAN}tg://proxy?server=${PROXY_HOST}&port=${PROXY_PORT}&secret=...${C_RESET}"
    echo -e "    (персональные ссылки — через API или Telegram бот)"
    echo ""
    echo -e "  ${C_BOLD}Webhook Bridge:${C_RESET}"
    echo -e "    https://<твой_домен>/webhook-proxy/<host>/<path>?<query>"
    echo ""
    echo -e "  ${C_BOLD}HTTP API:${C_RESET}"
    echo -e "    URL:       ${C_CYAN}http://${PROXY_HOST}:${API_PORT}${C_RESET}"
    echo -e "    Docs:      ${C_CYAN}http://${PROXY_HOST}:${API_PORT}/docs${C_RESET}"
    echo -e "    X-Api-Key: ${C_CYAN}${API_KEY}${C_RESET}"
    echo ""
    echo -e "  ${C_BOLD}Полезные команды:${C_RESET}"
    echo -e "    ${C_GRAY}sudo docker compose logs -f          ${C_RESET}— логи всех сервисов"
    echo -e "    ${C_GRAY}sudo docker compose restart          ${C_RESET}— перезапуск"
    echo -e "    ${C_GRAY}sudo docker compose ps               ${C_RESET}— статус контейнеров"
    echo -e "    ${C_GRAY}./install.sh --force-step=env        ${C_RESET}— перенастроить .env"
    echo -e "    ${C_GRAY}./install.sh --force-step=launch     ${C_RESET}— пересобрать и перезапустить"
    echo ""
    echo -e "  ${C_GRAY}Лог установки: ${LOG_FILE}${C_RESET}"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    # Очищаем лог только при полном --force или первом запуске
    if [[ "$FORCE" == true ]] || [[ ! -f "$STATE_FILE" ]]; then
        > "$LOG_FILE"
        [[ "$FORCE" == true ]] && rm -f "$STATE_FILE"
    fi

    header "MTProto Proxy + Webhook Bridge — Установщик"
    echo -e "  Лог: ${C_GRAY}${LOG_FILE}${C_RESET}"
    echo -e "  Состояние шагов: ${C_GRAY}${STATE_FILE}${C_RESET}"
    [[ "$FORCE" == true ]]       && warn "--force: все шаги будут выполнены заново."
    [[ -n "$FORCE_STEP" ]]       && warn "--force-step=${FORCE_STEP}: шаг будет выполнен заново."

    step_preflight
    step_packages
    step_docker
    step_env
    step_firewall
    step_launch
    step_verify
    show_summary
}

main
