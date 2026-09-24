# Установка и первичная настройка

Ориентировано на Windows-машину, на которой уже установлены и авторизованы
`claude` (Claude Code) и `opencode` (OpenCode CLI).
Quoroom их не устанавливает, не настраивает и не запускает: сессии
открывает человек, а брокер только разносит сообщения.

Дальше в командах `$AgentsChat` — каталог, куда вы склонировали репозиторий.
Задайте его один раз:

```powershell
$AgentsChat = "D:\AI\AgentsChat"   # подставьте свой
```

## 0. Предварительные требования

- Docker Desktop (с бэкендом WSL2), уже запущен.
- [mkcert](https://github.com/FiloSottile/mkcert) — для локального TLS-сертификата.
- Python 3.10+ на хост-машине (для брокера).
- [uv](https://docs.astral.sh/uv/) — чтобы поставить клиент `agentschat`
  для всех репозиториев (шаг 9). Без него подойдёт pipx.
- Права администратора один раз — чтобы прописать hosts-файл и установить
  корневой сертификат mkcert в системное хранилище.

## 1. Локальное имя сервера

Добавьте в `C:\Windows\System32\drivers\etc\hosts` (редактировать от имени
администратора) строку:

```
127.0.0.1 agentschat.local
```

## 2. TLS-сертификат (mkcert)

```powershell
mkcert -install
cd $AgentsChat\docker\caddy
mkdir certs
mkcert -cert-file certs\agentschat.local.pem -key-file certs\agentschat.local-key.pem agentschat.local
```

`mkcert -install` кладёт корневой CA в доверенное хранилище Windows — после
этого браузер будет доверять сертификату для `agentschat.local` без
предупреждений (это нужно проделать на каждой машине, с которой будете
открывать Element Web).

Сертификат выдаётся на ~2 года (максимум, который ещё принимают Chrome/Safari).
Дата истечения и команда для продления записаны в
`docker/caddy/certs/RENEWAL.md` — плюс на этот срок уже поставлено
напоминание.

## 3. Переменные окружения

```powershell
cd $AgentsChat\docker
copy .env.example .env
```

`SERVER_NAME` уже равен `agentschat.local`, менять не нужно (и нельзя будет
поменять после первого запуска без пересоздания БД).

## 3а. Токен регистрации (конфиг-файл, не .env)

У докер-образа Continuwuity `allow_registration` и `registration_token` не
читаются из переменных окружения (в отличие от `server_name`, `address` и
т.п.) — только из смонтированного конфиг-файла. Поэтому отдельно:

```powershell
cd $AgentsChat\docker\continuwuity
copy continuwuity.toml.example continuwuity.toml
```

Откройте `continuwuity.toml` и задайте `registration_token` — любую длинную
случайную строку (`allow_registration = true` уже стоит, не трогайте пока).
Этот файл смонтирован в контейнер через `CONTINUWUITY_CONFIG` в
`docker-compose.yml`.

ВАЖНО: не удаляйте заголовок `[global]` в начале файла — у Continuwuity все
ключи конфига лежат внутри этой секции, без неё сервер падает при старте с
`invalid type: boolean, expected a map`.

## 4. Запуск инфраструктуры

```powershell
cd $AgentsChat\docker
docker compose up -d
docker compose logs -f continuwuity   # Ctrl+C когда увидите, что сервер поднялся
```

Проверка: `https://agentschat.local` в браузере должен открыть Element Web
(с доверенным сертификатом, без предупреждений, если шаг 2 сделан на этой
машине).

Если меняете `continuwuity.toml` уже после первого запуска — контейнер сам
не перечитает файл, нужно `docker compose restart continuwuity`.

## 5. Регистрация аккаунтов (2 бота + вы)

Регистрация на сервере сейчас открыта по токену из `continuwuity.toml`.
Проще всего зарегистрировать все 3 аккаунта скриптом-помощником, который
делает двухшаговый Matrix User-Interactive-Auth за вас:

```powershell
cd $AgentsChat\bridge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# requests (в отличие от браузера и от самого моста) не читает системное
# хранилище сертификатов Windows, поэтому ему отдельно нужен путь к корню
# mkcert — вычисляем один раз в переменную и переиспользуем:
$caRoot = "$(mkcert -CAROOT)\rootCA.pem"

# Пароли ниже — придумайте свои, это учётки только для локального сервера.
# --registration-token — то же значение, что вы вписали в continuwuity.toml.
.venv\Scripts\python register_account.py --homeserver https://agentschat.local `
    --username claude-code --password "..." --registration-token "<registration_token из continuwuity.toml>" --ca-bundle $caRoot

.venv\Scripts\python register_account.py --homeserver https://agentschat.local `
    --username opencode --password "..." --registration-token "<...>" --ca-bundle $caRoot

# И ваш личный аккаунт-наблюдатель:
.venv\Scripts\python register_account.py --homeserver https://agentschat.local `
    --username andrey --password "..." --registration-token "<...>" --ca-bundle $caRoot
```

Каждый вызов печатает `user_id` / `access_token` / `device_id` — для двух
ботов сохраните эти три значения, они понадобятся в `bridge/config.yaml` на
шаге 7. Для своего личного аккаунта просто запомните логин/пароль — им вы
будете заходить в Element Web как обычный человек.

Если всё равно увидите `CERTIFICATE_VERIFY_FAILED` — скрипт сам подскажет
именно эту команду в сообщении об ошибке. Более грубый вариант —
`--no-verify-ssl` вместо `--ca-bundle` (полностью отключает проверку
сертификата, но для разовой локальной регистрации это приемлемо).

Брокер этой проблемы не унаследует: он основан на aiohttp, а не на requests,
и aiohttp на Windows нормально читает системное хранилище сертификатов —
`verify_ssl: true` в `config.yaml` должен работать сразу после
`mkcert -install`, без аналога `--ca-bundle`.

**После того как все 3 аккаунта созданы**, закройте регистрацию: в
`continuwuity.toml` поставьте `allow_registration = false` и выполните
`docker compose restart continuwuity`.

## 6. Создание общей комнаты

1. Зайдите в `https://agentschat.local` под своим личным аккаунтом (`andrey`).
2. Создайте комнату, например `agents` (не обязательно делать её публичной —
   это локальный сервер, публичность ничего не защищает и не открывает
   наружу).
3. Пригласите (Invite) в неё `@claude-code:agentschat.local`,
   `@opencode:agentschat.local`.
4. Принимать приглашения вручную НЕ нужно — брокер сам вступает в комнату
   при старте. Достаточно, чтобы боты были приглашены на шаге 3.
5. Откройте именно нужную комнату (напр. **General**, а не пространство!)
   -> Room settings -> Advanced -> скопируйте "Internal room ID"
   (вид `!AbCdEfGh...:agentschat.local`, начинается с `!`).

   ВАЖНО: `room_id` — это ID самой комнаты, а не имя пространства (space).
   Значение должно начинаться с `!` (внутренний ID) или `#` (алиас комнаты).
   Имя пространства вроде `spacerobots:agentschat.local` НЕ подойдёт —
   брокер не найдёт комнату и будет молча игнорировать все сообщения.

## 7. Настройка брокера

```powershell
cd $AgentsChat\bridge
copy config.example.yaml config.yaml
```

В `config.yaml`:

- вставьте `room_id`, полученный на шаге 6;
- для каждого агента вставьте `user_id` / `access_token` / `device_id`,
  полученные на шаге 5.

Больше там настраивать нечего: режимы доставки (`delivery`) уже проставлены
и менять их не нужно. Файл `config.example.yaml` перечисляет всё, что брокер
читает, и ничего сверх того.

## 8. Запуск брокера

Брокер — один процесс на всю систему, не по одному на агента.

```powershell
cd $AgentsChat\bridge
.venv\Scripts\python.exe -X utf8 -m sessionchat.broker --config config.yaml --verbose
```

В логе должна появиться единственная строка вида:

```
БРОКЕР ГОТОВ комната=!AbCdEf...:agentschat.local порт=8770
```

Держите это окно открытым: реестр подключённых сессий живёт в памяти
процесса. Флаг `--agents claude-code,opencode` ограничивает список
обслуживаемых агентов — удобно, пока вы вводите их по одному.

## 9. Подключить чат в любом репозитории

Сессии входят в комнату командой `agentschat` и скиллом `chatlogin`. Ни то,
ни другое не кладётся в репозитории: клиент ставится один раз на машину, и
после этого `/chatlogin` работает в сессии, открытой в любом проекте, —
включая сам Quoroom.

Поставить CLI:

```powershell
uv tool install --editable $AgentsChat\bridge
agentschat --help
```

uv кладёт `agentschat.exe` в `~/.local/bin` (`%USERPROFILE%\.local\bin`).
Если `agentschat --help` отвечает, что команда не найдена, — этого каталога
нет в PATH: `uv tool update-shell` добавит его в PATH пользователя, после
чего откройте новый терминал и перезапустите CLI агентов, чтобы они
унаследовали новый PATH.

Без uv то же делает pipx: `pipx install --editable $AgentsChat\bridge`
(`pipx ensurepath` — аналог `uv tool update-shell`).

Разложить скиллы, команду и плагин по каталогам Claude Code (`~/.claude`) и
OpenCode (`~/.config/opencode`):

```powershell
agentschat install
```

Команда печатает строку на каждый файл и в конце просит перезапустить
открытые сессии: запущенные нового набора не увидят. Ключи `--claude` и
`--opencode` ограничивают установку одним CLI.

Что установщик трогает, записано в `~/.agentschat/kit.json`. Если на месте
файла набора уже лежит чужой файл с другим содержимым, установка отменяется
целиком, ничего не записав, и называет этот файл; перезаписать его можно
только явно, `agentschat install --force`.

**Обновление.** Установка editable, поэтому после `git pull` новый код CLI
работает сразу. Скиллы и плагин — копии, сами они не обновятся: после
каждого `git pull` выполните `agentschat install` ещё раз и перезапустите
открытые сессии. Иначе скиллы будут описывать сессиям прежний CLI.

**Удаление.**

```powershell
agentschat uninstall
uv tool uninstall quoroom
```

`uninstall` убирает только то, что записано в манифесте. Файл, который вы
правили руками после установки, он называет и оставляет; удалить и его —
`agentschat uninstall --force`.

## 10. Подключение сессий

Для каждого агента: откройте сессию в каталоге своего проекта и вызовите
в ней `/chatlogin`.

У OpenCode имя можно назвать прямо в вызове: `/chatlogin terra` — сессия
войдёт в комнату как участник `terra`, а не как `opencode`. Так один процесс
OpenCode держит в чате несколько личностей: скажем, сессию на модели OpenAI
и сессию на модели через Ollama, каждую под своим именем. Имя должно быть
заведено в `config.yaml` наравне с остальными агентами, с `delivery: "plugin"`.

Скилл, команду и плагин обе программы берут из каталогов пользователя, куда
их положил шаг 9. Сессия сама выполнит `login` и скажет, что подключена.
Проверить, кто на связи, можно из любого каталога:

```powershell
agentschat status
```

## 11. Проверка

В Element Web под своим личным аккаунтом напишите в комнату:

```
@claude-code привет, представься одним предложением
```

Ответ должен появиться в комнате в течение нескольких секунд. Так же
проверьте `@opencode`.

Если ответа нет — смотрите лог брокера: в нём видно и обращение по HTTP от
сессии, и отказ, если что-то не так.

## Дальнейшие шаги

- Прочитать [SESSION_BRIDGE.md](SESSION_BRIDGE.md): там устройство брокера,
  способы доставки и журнал живых проверок.
- Не забыть закрыть регистрацию на сервере, если ещё не сделали (шаг 5).
