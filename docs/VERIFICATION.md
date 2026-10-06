# Живые сценарии установщика: Windows выполнен, Linux ожидает прогона

Установщик проверен автоматическими тестами на обеих платформах и
функциональными прогонами агента в одноразовом контейнере `ubuntu:24.04` со
своим движком Docker. Два сценария ниже выполняет человек. Сценарий 1
(Windows) выполнен 5 октября 2026, запись - в конце этого раздела. Сценарий 2
(Linux) не выполнен: Linux не записан как проверенный живьём, и результаты не
пишутся - только сюда, после прогона. Секреты в отчёте - масками.

## Как записывать результат

Когда сценарий выполнен, добавьте раздел с датой и таблицей:

| Что | Значение |
|-----|----------|
| Дата прогона | 2026-10-05 |
| Сборка Windows | |
| Docker Desktop, версия движка | |
| Образ Continuwuity и что он сам о себе сообщает | |
| Claude Code, версия | |
| OpenCode, версия | |
| Итог по шагам: что прошло, что нет | |

## Сценарий 1. Windows: обе роли на живой машине

Границы сценария (story, гейт 6): идёт по живой установке владельца. Проверяет
установку и повтор, снятие и переустановку участника, снятие и переустановку
сервера. **Очистку сервера живьём не запускать**: один движок Docker держит
один стенд под фиксированными именами контейнеров, и «одноразовая» установка
поделила бы живые тома. Сценарий заканчивается поднятым стендом.

Про `stop.ps1`: он ищет брокер по командной строке по всей машине, поэтому
все команды снятия выполняйте **только из живой копии репозитория** - прогон
из другого клона погасит живой брокер.

### Шаг 0. Подготовка

```powershell
cd $AgentsChat
.\stop.ps1
docker compose -f docker\docker-compose.yml ps -a      # пусто
Test-Path bridge\state\agentschat.db                     # True: состояние есть
```

Стенд остановлен осознанно: сценарий снимает и поднимает его сам.

### Шаг 1. Установка сервера

```powershell
.\install.ps1 --role server --admin-user <ваш логин>
```

Ожидать: файлы и сертификат «уже сделано» (стенд собран руками, установщик
их не переписывает), «Поднять инфраструктуру: готово», а затем остановка с
кодом `3` на шаге «Закрыть регистрацию» - на живой машине
`allow_registration = true`. Ничего не удалено и не заменено.

Закройте регистрацию и повторите:

```powershell
# в docker/continuwuity/continuwuity.toml: allow_registration = false
docker compose -f docker\docker-compose.yml restart continuwuity
.\install.ps1 --role server --admin-user <ваш логин>
```

Ожидать: код `0`, адрес брокера и адрес Element в отчёте, брокер отвечает.

### Шаг 2. Повтор установки

```powershell
.\install.ps1 --role server --admin-user <ваш логин>
```

Ожидать: код `0`, ни одного «готово» там, где файл уже был, и ни одного
перезаписанного файла. Если что-то оказалось «готово» - запишите это, это
находка.

### Шаг 3. Вопрос имени аккаунта

```powershell
.\install.ps1 --role server
```

Ожидать: вопрос «Имя локального аккаунта человека, под которым он войдёт в
Element:». Введите существующий
логин. Дальше пароль не спрашивают: аккаунт на сервере уже есть, шаг возвращается
сразу. Строка шага при этом «Завести аккаунт человека: готово», а не «уже
сделано»: без `--admin-user` установщик не знает имени, пока не спросит, и
заранее отметить шаг сделанным не может. Остальные шаги - «уже сделано». Это и есть проверка интерактивного вопроса имени - единственная, что
достижима на этой машине.

### Шаг 4. Граница ввода пароля

Вопрос пароля на живой машине не достать: до него не доходит дело с
существующим аккаунтом. Проверьте саму границу ввода прямо из `bridge/`, в
живой консоли Windows, где есть терминал:

```powershell
cd $AgentsChat\bridge
$env:PYTHONPATH = "."
.venv\Scripts\python.exe -X utf8 -c "from sessionchat.installer.boundaries import ask_secret; print('совпало, символов:', len(ask_secret('Пароль админа: ')))"
cd $AgentsChat
```

Ожидать: приглашение `Пароль админа:`, затем `Повторите пароль: `, и **ни
одного символа на экране** - ввод не отображается. Введите пароль и повторите
его: в конце печатается `совпало, символов: <длина>`, сам пароль не
печатается. Введите разные - команда падает с `пароли не совпали`.

### Шаг 5. Участник

```powershell
.\install.ps1 --role participant
```

Ожидать: «Брокер отвечает на http://127.0.0.1:8770», строка про перезапуск
сессий (или «Набор на месте и не менялся», если набор уже стоит) и шаг
`/chatlogin`.

### Шаг 6. Обмен в обе стороны, вне репозитория Quoroom

Откройте сессию Claude Code и сессию OpenCode в каталоге постороннего
проекта. В каждой вызовите `/chatlogin`. В Element Web напишите в комнату
`@claude-code <вопрос>` и `@opencode <вопрос>` - ответы должны прийти в обе
сессии. Потом пусть один агент напишет другому: `@opencode передай
@claude-code, что связь есть`. Ожидать: обмен в обе стороны.

### Шаг 7. Снятие участника, повтор снятия, переустановка

```powershell
.\install.ps1 --role participant --remove
```

Ожидать: набор убран, **пакет `quoroom` остался**: на этой машине он поставлен
руками через uv и записи у установщика нет, поэтому отчёт печатает «пакет
quoroom (uv)» и оставляет его. Файлы сессий в `~/.agentschat` остались, и
строка о них говорит, что вернуться в комнату можно новым входом: пакет
остался на месте, поэтому обещания «вернётся через `/chatlogin`» нет.

```powershell
.\install.ps1 --role participant --remove
```

Ожидать: код `0`, «уже сделано», пакет по-прежнему остался.

```powershell
.\install.ps1 --role participant
```

Ожидать: код `0`, `/chatlogin` работает без новой регистрации.

### Шаг 8. Снятие сервера, повтор снятия, переустановка

```powershell
.\install.ps1 --role server --remove
```

Ожидать: `compose ps -a` пуст, тома на месте, `continuwuity.toml`,
`config.yaml`, оба сертификата и `bridge/state/agentschat.db` на месте (файла
`server-accounts.json` на этой машине нет: пароли не сохранялись), отчёт
называет оставленное с причиной.

```powershell
.\install.ps1 --role server --remove
```

Ожидать: код `0`, «уже сделано» на обоих шагах.

```powershell
.\install.ps1 --role server --admin-user <ваш логин>
```

Ожидать: подъём на тех же томах, переписка в комнате на месте, код `0`.

### Шаг 9. Возврат машины в рабочее состояние

```powershell
.\start.ps1
```

Ожидать: брокер отвечает на 8770, `compose ps` показывает три контейнера.
Регистрации хранятся в SQLite и должны пережить перезапуск брокера; сессии,
молчавшие дольше 3 минут, нужно подключить заново. Восстановление вживую не
проверено: запишите результат здесь.

## Сценарий 2. Linux: обе роли в лаборатории

Лаборатория - одноразовый контейнер `ubuntu:24.04` со своим движком
`docker:dind`, проект `quoroom-linux-lab`. Живой стенд Windows она не видит и
не трогает. Всё выполняется **из Git Bash** (или любого Linux), не из
PowerShell.

Ожидаемые строки ниже русские, поэтому каждый вызов `install.sh` идёт с
`--lang ru`: по умолчанию установщик печатает английский текст.

Живой доступ к Element: человек останавливает стенд Windows, публикует 443
движка лаборатории на 443 хоста и открывает `https://agentschat.local` в
браузере Windows, приняв предупреждение о сертификате (CA контейнера Windows не
доверяет). Проверка занятости 443 в лаборатории смотрит английские состояния
`netstat` (`LISTEN`/`LISTENING`), а на локализованной Windows из них
срабатывает только проверка портов Docker, поэтому порт освобождайте заранее и
проверьте его сами.

### Шаг 0. Подготовка

В PowerShell:

```powershell
cd $AgentsChat
.\stop.ps1
Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue   # пусто: порт свободен
```

В Git Bash:

```sh
cd tools/linux-container
./run.sh up --publish-443
./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --help'
```

Ожидать: копия репозитория с текущим кодом в `/home/lab/repo`, `--help`
печатает ключи.

### Шаг 1. Строка в hosts машины

```sh
printf '127.0.0.1 agentschat.local\n' | ./run.sh exec-root \
    'grep -q agentschat.local /etc/hosts || cat >> /etc/hosts'
./run.sh exec 'getent hosts agentschat.local'
```

### Шаг 2. Первый прогон установщика: он выпускает сертификат

```sh
./run.sh exec 'cd /home/lab/repo && QUOROOM_ADMIN_PASSWORD=<пароль> ./install.sh --lang ru --role server --admin-user labadmin'
```

Ожидать: шаги до доверия - «готово» или «уже сделано» (проверки
инструментов и hosts), затем код `3` на «Проверить доверие к
сертификату» с готовой командой. Это правильно: сертификат выпускает
установщик от пользователя `lab`, и только теперь корень можно ставить в
хранилище.

### Шаг 3. Доверие корню mkcert

```sh
CAROOT=$(./run.sh exec 'cd /home/lab/repo && mkcert -CAROOT')
./run.sh exec-root "cd /home/lab/repo && CAROOT=$CAROOT mkcert -install"
```

Имя `CAROOT` обязательно: под root свой каталог mkcert, и без него доверие было
бы выдано не тому корню, которым подписан выпущенный сертификат.

### Шаг 4. Продолжение установки до комнаты

```sh
./run.sh exec 'cd /home/lab/repo && QUOROOM_ADMIN_PASSWORD=<пароль> ./install.sh --lang ru --role server --admin-user labadmin'
```

Ожидать: аккаунты заведены, регистрация закрыта, код `3` на «Записать
комнату» с инструкцией.

Комнату в этом сценарии создаёт человек, а не помощник: откройте в браузере
Windows `https://agentschat.local`, войдите под `labadmin` (пароль из
`QUOROOM_ADMIN_PASSWORD`), создайте комнату, пригласите
`@claude-code:agentschat.local` и `@opencode:agentschat.local`, затем Room
settings -> Advanced -> Internal room ID.

```sh
./run.sh exec 'cd /home/lab/repo && QUOROOM_ADMIN_PASSWORD=<пароль> ./install.sh --lang ru --role server --admin-user labadmin --room-id <комната>'
```

Ожидать: код `0`, адрес брокера и адрес Element в отчёте.

### Шаг 5. Участник

```sh
./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --role participant'
./run.sh exec 'cd /home/lab/repo && AGENTSCHAT_URL=http://127.0.0.1:8770 agentschat status'
```

Ожидать: код `0`, «Брокер отвечает». Сессий в этот момент никто не открывал,
поэтому `agentschat status` отвечает, а каждый агент в нём «не подключён». Вход -
в шаге 6.

### Шаг 6. Обмен в обе стороны

Внутри лаборатории нет ни `claude`, ни `opencode`, поэтому обмен проверяется
клиентом напрямую. Адрес брокера клиент берёт из `AGENTSCHAT_URL`, поэтому
задавайте его явно:

Вход, затем сообщение из лаборатории в комнату:

```sh
./run.sh exec 'cd /home/lab/repo && AGENTSCHAT_URL=http://127.0.0.1:8770 agentschat login --agent claude-code'
./run.sh exec 'cd /home/lab/repo && AGENTSCHAT_URL=http://127.0.0.1:8770 agentschat say --agent claude-code "@human проверка связи"'
```

Ожидать: сообщение от `claude-code` видно в комнате в Element.

Теперь обратное направление. Запустите ожидание и, пока оно висит, напишите в
Element `@claude-code <вопрос>`:

```sh
./run.sh exec 'cd /home/lab/repo && AGENTSCHAT_URL=http://127.0.0.1:8770 agentschat wait --agent claude-code'
```

Ожидать: `wait` печатает ваше сообщение в конверте и завершается: он возвращается
после первого же полученного сообщения. Для второго сообщения запустите `wait`
заново. Сессии `opencode` в лаборатории нет, поэтому `@opencode` не проверяется.

### Шаг 7. Снятие и повтор снятия

```sh
./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --role both --remove'
./run.sh exec 'cd /home/lab/repo && docker volume ls --format "{{.Name}}"'
./run.sh exec 'cd /home/lab/repo && ls bridge/state docker/continuwuity/continuwuity.toml'
./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --role both --remove'
```

Ожидать: тома на месте, `continuwuity.toml` и состояние брокера на месте,
файлы сессий участника на месте, второй прогон - «уже сделано» и код `0`.

### Шаг 8. Повторная установка

```sh
./run.sh exec 'cd /home/lab/repo && QUOROOM_ADMIN_PASSWORD=<пароль> ./install.sh --lang ru --role both --admin-user labadmin'
```

Ожидать: код `0`, существующая конфигурация не перезаписана, переписка в
комнате на месте.

### Шаг 9. Очистка по ролям

Сначала сервер, и проверить, что данные участника целы:

```sh
printf 'PURGE\n' | ./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --role server --remove --purge'
./run.sh exec 'cd /home/lab/repo && ls -a $HOME/.agentschat && cat $HOME/.agentschat/kit.json | head -3'
```

Ожидать: тома сервера исчезли, а `~/.agentschat` и набор на месте. Брокер
остановлен снятием сервера, поэтому `agentschat status` здесь не вызывается:
он ответил бы, что брокер недоступен.

Потом участник:

```sh
printf 'PURGE\n' | ./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --role participant --remove --purge'
./run.sh exec 'cd /home/lab/repo && ls -a $HOME/.agentschat'
printf 'PURGE\n' | ./run.sh exec 'cd /home/lab/repo && ./install.sh --lang ru --role participant --remove --purge'
```

Ожидать: файлы сессий удалены, повторный прогон - код `0` без вопроса.

### Шаг 10. Возврат машины в рабочее состояние

```sh
./run.sh down
```

В PowerShell: `.\start.ps1` в корне репозитория, затем `/chatlogin` в сессиях.

## Запись: сценарий 1 (Windows) - 5 октября 2026

| Что | Значение |
|-----|----------|
| Дата прогона | 2026-10-05 |
| Кто выполнял | владелец машины, по сценарию 1 выше |
| Сборка Windows, Docker, образ Continuwuity, версии Claude Code и OpenCode | не записаны |
| Итог по шагам | владелец сообщил: все шаги отработали штатно |
| Наблюдение, показанное в чате | шаг 3, `.\install.ps1 --role server` без `--admin-user`: все шаги «уже сделано», кроме «Завести аккаунт человека: готово»; имя спросили, пароль не спрашивали. Совпадает с кодом, сценарий дополнен этой строкой |
| Находка | опечатка «Docker-демен» в названии шага (исправлена на «демон») |

Запись неполная: по шагам, кроме шага 3, нет ни вывода, ни кодов возврата,
есть только сообщение владельца. Сценарий 2 (Linux) не выполнялся.

# Спайк: чтение комнаты вперёд от записанной позиции — 11 сентября 2026

Зачем это читать: очередь подписки живёт в памяти брокера и теряется вместе с
его процессом. Пока брокер мёртв, в комнату могут написать, адресовав сессии;
человек в Element видит сообщение в комнате и считает его доставленным, а
единственная запись о том, что оно причитается сессии, погибла с очередью.
Store очередь нарочно не хранит — только ACK-позицию. Поэтому в момент
возврата держателя токена (первый опрос после рестора, reattach) брокеру
нужно восстановить очередь, и единственный способ — перечитать комнату у
Matrix вперёд от ACK-позиции. При старте брокера, пока ни один держатель
токена не вернулся, читать нечего и не для кого: очередь некому отдать, а
подписка, чья сессия не вернётся, умрёт по счётчику молчания, не потратив ни
одного обращения к Matrix.

Сам спайк проверил, умеет ли Continuwuity превращать event id в
pagination-токен и ведёт ли себя предсказуемо чтение вперёд.

Стенд: Continuwuity (ghcr.io/continuwuity/continuwuity, digest
`sha256:fdf3cd0f...`, Matrix API до v1.18) в локальном Docker, комната
General, запросы от имени двух существующих аккаунтов агентов через
`https://agentschat.local/_matrix/client/v3`. Проверялось живыми запросами,
не по документации.

1. `GET /rooms/{id}/context/{eventId}?limit=0` реализован. Возвращает
   `start` и `end` — и оба равны потоковой позиции самого события
   (`start == end`); `events_before` / `events_after` пусты. Позиция —
   монотонное целое, передаётся строкой (`"3155"`, `"4042"`).
2. `GET /rooms/{id}/messages?dir=f&from=<token>` читает события **строго
   после** позиции токена: сам якорное событие в выдачу не попадает.
   Порядок выдачи соответствует порядку поступления; на живом краю выдача
   пуста (`chunk: []`, поле `end` отсутствует). Токен, снятый до отправки
   нового сообщения, после отправки возвращает ровно это сообщение.
3. `prev_batch` из sync-таймлайна — тот же сорт токена: чтение вперёд от
   него начинается **после** первого события таймлайна, то есть первое
   событие синхронизации в выдачу не попадает (совпадает с п. 2).
4. Токен переживает перезапуск homeserver (`docker restart`): токен `"4042"`
   сохранён до перезапуска, после — `/messages` от него отработал, `/context`
   работает. Токен одного аккаунта используется другим аккаунтом (токен —
   позиция в потоке комнаты, не сессионный объект).
5. Выдача `/messages` ограничена сверху страницей: при `limit=500` пришло
   100 событий и непустой `end`; следующая страница дочитала остаток.
   Комната мала (128 событий), поведение при выходе за границу истории
   проверено лишь как отсутствие ошибки; полного теста retention-границы
   спайк не проводил.

Аномалия, которая оказалась не аномалией: первое сравнение показало
«28 пропавших событий» при чтении вперёд от глубокого токена. Разбор
показал ошибку сравнения — «пропавшими» были события до якоря. Полное
чтение вперёд от начала комнаты даёт ровно все события после `m.room.create`.

# Функциональный прогон в лаборатории: homeserver и Caddy - 4 октября 2026

Лаборатория `tools/linux-container`: Ubuntu 24.04 на своём `docker:dind`, HOME
`/home/lab`, порты хоста не публиковались. Образ
`ghcr.io/continuwuity/continuwuity:latest`, сам себя называющий conduwuit
26.9.1. Это функциональный прогон в лаборатории, а не живой сценарий из
истории: живой прогон делает человек с Element в браузере, и его ждёт задача
08. Что установщик делал на этих данных - в отчёте задачи
[.development/reports/task-local-installers-06-server-install.md](../.development/reports/task-local-installers-06-server-install.md).

Живой стенд Windows при этом не трогали: `agentschat-caddy`,
`agentschat-element` и `agentschat-continuwuity` остались подняты, 14 томов и
7 сетей до и после, остатков `quoroom-linux-lab` нет.

Внешние факты, ради которых эта запись и ведётся:

1. **Серверный токен регистрации приходит в лог.** На свежей базе настроенный в
   `continuwuity.toml` токен первый аккаунт не регистрирует, а сервер печатает
   свой: `using the registration token <issued-token>`. Настроенный токен
   начинает работать после первого аккаунта. Подробности и доказательства -
   [.development/bugreports/closed/registration-token-first-account.md](../.development/bugreports/closed/registration-token-first-account.md).
2. **Идентификаторы комнат у свежего Continuwuity идут без домена.**
   Комната, созданная для прогона, это `!sA9OkuYMoPu9zQG6qZ-S7Gba8HNS2JbfGoAZmgqwXy8`,
   без `:agentschat.local`. Вход в такую комнату с дописанным доменом идёт по
   федерации и падает с `M_UNKNOWN No server available to assist in joining`,
   даже для пользователя, который уже в комнате. Псевдоним, наоборот, всегда
   называет сервер.
3. **Caddy отвечает `502`, пока homeserver перезапускается.** Ответ шлюза нельзя
   считать признаком поднявшегося сервера.
4. **`GET /register/available` отвечает `200 {"available": true}` для свободного
   имени и `400 M_USER_IN_USE` для занятого**, без авторизации.
5. **Закрытая регистрация отвечает `403 M_FORBIDDEN "This server is not
   accepting registrations at this time."`**, и этот признак отличается от `401`
   неверного токена. Список способов регистрации (`flows` в ответе UIA) и
   `available` при этом не меняются, и для проверки не годятся.

Что живьём не проверено: Windows (ветка `platform="windows"` покрыта только
тестами), Element в браузере, сервер, собранный руками. Разбор срока
сертификата - в отчёте задачи local-installers-06.

# Снятие роли сервера: поведение Docker Engine (функциональная проверка, не живой сценарий) - 4 октября 2026

Зачем это читать: снятие и очистка сервера опираются на поведение команд
Docker, которое нигде в коде не выражено, потому что это не наш код. Проверено
настоящим Docker Engine 28.4.0 на Windows 11, на одноразовом проекте
`agentschat-lab` (свой `name:` в compose-файле, без `container_name` и без
публикации портов - иначе второй стенд на одном движке невозможен).

Живой стенд хоста не трогали: `agentschat-caddy`, `agentschat-element` и
`agentschat-continuwuity` остались `Up 8 hours` до и после, `docker_caddy-data`,
`docker_caddy-config`, `docker_continuwuity-data`, сеть `docker_agentschat` и
остальные 14 томов на месте. Том и сеть лаборатории убраны, каталог лаборатории
удалён.

1. **`docker compose -f <file> down` без `-v` оставляет именованные тома.**
   Контейнер и сеть проекта удалены (код 0), `docker volume inspect
   agentschat-lab_caddy-data` после этого отвечает 0 - том жив. Ровно то поведение,
   на котором стоит разница между снятием (данные целы) и очисткой.
2. **`ps -q` не видит остановленный контейнер, `ps -a -q` видит.** После
   `compose stop caddy` команда `ps -q` вернула пустой вывод с кодом 0, а
   `ps -a -q` - идентификатор контейнера. Поэтому проверка шага снятия
   спрашивает `ps -a -q`: без `-a` остановленный или упавший контейнер выглядел
   бы как «уже снято».
3. **`docker volume inspect` различает «том есть» и «тома нет», а `docker volume
   rm` - нет.** `inspect` даёт код 0 на существующем томе и 1 на отсутствующем.
   `rm` тоже даёт 0 и 1, но по разным причинам: «нет такого тома» и «том занят».
   Поэтому шаг томов спрашивает `inspect` перед `rm`: удалённый снаружи том должен
   считаться удалённым, иначе очистка падала бы навсегда, а занятый том должен
   падать.
4. **`down` на проекте без контейнеров завершается кодом 0.** Повторное снятие
   не требует особой обработки.
5. **Контейнер без фиксированного имени не мешает второму стенду, а фиксированное
   имя мешает.** В лаборатории контейнер назывался `agentschat-lab-caddy-1`.
   Это граница применимости лаборатории на одном движке, а не свойство
   установщика.

Полный цикл снятия и очистки прогнан в `tools/linux-container` (свой движок
`docker:dind`, проект `quoroom-linux-lab`, порты хоста не публикуются) на копии
рабочей папки с незакоммиченным кодом задачи: установка сервера и участника,
снятие сервера, повторная установка, очистка `--role both --remove --purge`,
повтор очистки и повтор снятия, плюс очистка при остановленном демоне и её
повтор после подъёма. Живой стенд Windows всё это время не тронут: три
`agentschat-*`, 14 томов и 7 сетей до и после. Подробности, включая то, что
лаборатория не может вернуть демон при остановленном `dind` без пересоздания
машины, - в закрытой карточке task-local-installers-07-server-removal.md.

Что живьём не проверено: Windows-ветка снятия на стенде человека
(`platform="windows"` покрыта только тестами), Element в браузере, сервер,
собранный руками, и очистка при живом демоне, когда часть томов занята.

# Проверка моста — 6 сентября 2026

> **Отменено.** Проверки относятся к мосту первого поколения
> (удалено из дерева, тег `v1.0.0-rc.1`). Журнал живых проверок брокера — в
> [SESSION_BRIDGE.md](SESSION_BRIDGE.md), раздел «Живая проверка».


## Причина отсутствия ответов

Алиас `#general.spacerobots:agentschat.local` разрешался в пространство
`spacerobots` с `m.room.create.content.type = m.space`, а не в General.
Все три бота состояли только в пространстве. События сообщений дочерней
комнаты не поступали в его timeline.

Рабочая комната General:
`!fwDrchLMKCsaN0YJ1G5CrlkK-EucWO_oFlIYhR4uLgs`.
Боты вступили в неё; этот ID записан в `bridge/config.yaml`.
Теперь мост проверяет `m.room.create` при запуске и явно отклоняет пространство.

## Проверенное поведение

- matrix-nio **0.26.0**: первичная синхронизация и доставка нового сообщения
  через инкрементальный `/sync` в callback `RoomMessageText` работают.
  Проверено с `full_state=True`, как в рабочем мосте. Оснований заменять nio
  или обходить инкрементальную синхронизацию в этом стенде не обнаружено.
- Claude Code **2.1.260**: запуск через явный путь к CLI из установленного
  Claude, без `--bare`; используется существующая авторизация по подписке.
- Codex CLI **0.153.4** из приложения: `--sandbox workspace-write`,
  `--skip-git-repo-check`, результат через `--output-last-message`.
  npm-версия 0.147.0 не поддерживала выбранную пользователем модель.
- OpenCode **1.18.29**: установлен локально в `bridge/.tools`, используется
  существующая авторизация Ollama Cloud и модель `ollama-cloud/gpt-oss:120b`.
- Дочерние CLI получают закрытый stdin: интерактивного оператора у моста нет.
- Все три проверки Matrix → nio → реальный CLI → Matrix завершились успешно.

Явные пути CLI сохранены только в локальном конфиге. После обновления приложений
проверьте их: каталог установленной версии Claude или Codex может измениться.

## Запуск и диагностика

Три моста запущены в фоне. Их журналы: `bridge/logs/<agent>.log`, PID запуска:
`bridge/logs/<agent>.pid`. PID — запись о запуске, а не проверка активности.
В журнале первой фоновой сессии кириллица может быть представлена как `\uXXXX`.

После перезагрузки мосты автоматически не запускаются. Запуск вручную:

```powershell
cd D:\AI\AgentsChat\bridge
.\run_all.ps1
```

Не запускайте второй экземпляр для уже работающего агента: он тоже будет
реагировать на сообщения. Сначала завершите соответствующий процесс моста.

Адресация в General: `@claude-code`, `@codex`, `@opencode`.
Каждое сообщение пока создаёт отдельную CLI-сессию без истории разговора.

## Воспроизводимые проверки

Все команды выполняются из `D:\AI\AgentsChat\bridge`.

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\ruff check matrix_bridge.py tests
.venv\Scripts\ruff format --check matrix_bridge.py tests
.venv\Scripts\python -m unittest discover -s tests -v
```

Обычный запуск выполняет пять unit-тестов и пропускает live-проверки.
Они покрывают запуск в комнате, отказ для пространства, ошибку чтения состояния,
ошибку вступления и отсутствие интерактивного stdin. Новая проверка типа комнаты
покрыта unit-тестами полностью; весь прежний код моста на 100% не покрыт.

Для полной проверки предварительно запустите три моста. Команда ниже отправляет
три тестовых запроса в General и вызывает реальные модели:

```powershell
$env:AGENTSCHAT_LIVE = '1'
.venv\Scripts\python -m unittest discover -s tests -v
Remove-Item Env:AGENTSCHAT_LIVE
```

Результат проверки: **8 тестов прошли**, включая три live-теста (14,65 с).
Тестовые запросы и ответы оставлены в General.

# Гейт публичного релиза: чистый прогон на английском и на русском - ждёт человека (подготовлено 6 октября 2026)

Сценарий выполняет человек (владелец или тот, кого он назовёт), один раз, на
кандидате в релиз: на коммите, где слиты задачи english-release-01 - 19 и 21 и
зелёные автоматические проверки. Агент результат не записывает: поля в конце
раздела пустые и заполняются после прогона.

Что без него невозможно. Ни один автоматический тест не показывает, дошёл ли
чужой человек от клона репозитория до обмена сообщениями между двумя живыми
агентами и увидел ли он по дороге только английский. Без записи английского
прогона как «проходит» владелец не открывает репозиторий (условие карточки
задачи english-release-20). Конкретно вживую проверяется то, что тестами
закрыто только на подменах: экран установщика с шагами для человека; привязка
сессии плагином OpenCode по строке `AGENTSCHAT-RESULT` при английском выводе;
конверт, который получает живая сессия; тексты скиллов, по которым агент
действует; уведомление о пределе глубины в Element.

Две вещи в этом сценарии наблюдаются, а не проверяются на соответствие
ожиданию, потому что ожидание следует из кода, а не из прежнего поведения:
какой язык у клиента до первого ответа брокера (шаг Р1) и какой язык у набора,
если он поставлен не на язык комнаты (раздел «Выведено из кода, не запускалось»,
п. 2).

## Установлено до прогона (находки; Docker, Element и сессии CLI не использовались)

1. `agentschat --help` и справка подкоманд на машине без
   `~/.agentschat/language` английские; с файлом, где написано `ru`, - русские
   (временный профиль пользователя, брокер не нужен).
2. Модуль установщика: `--help` английский по умолчанию и русский с
   `--lang ru`; `--lang fr` даёт код `2` и английский текст
   `AGENTSCHAT: unsupported language 'fr', available: en, ru`.
3. Без файла `language` и без брокера клиент говорит по-английски: проверено на
   временном профиле (`agentschat say --agent claude-code hi` отказывает
   по-английски со строкой `AGENTSCHAT-RESULT` и кодом `not_logged_in`).
4. `agentschat install --json` на временном каталоге: чужой файл на месте
   файла набора даёт документ с кодом `conflict`, код возврата `5`, ничего не
   записано; тот же отказ без `--json` печатает английский текст и даёт код
   `1`; после удаления чужого файла установка проходит с кодом `0`, повтор -
   `unchanged`.

## Выведено из кода, не запускалось (по коду; пересматривается без повторной проверки)

1. Справку клиент берёт из запомненного языка: он известен до разбора
   аргументов (`client.py`, `client_language.py`). Значит, в русской комнате
   справка по-русски только после того, как клиент хотя бы раз получил ответ
   брокера.
2. Язык набора (скиллы, команда `/chatlogin`) - это `--lang` установщика или
   `agentschat install`, а не язык комнаты: установщик участника кладёт набор
   раньше, чем обращается к брокеру (`docs/INSTALL.en.md`, «Room language»).
   Следствие для сценария: русский прогон ставит и сервер, и участника с
   `--lang ru`.
3. Состав набора: `bridge/sessionchat/kit/en/` и `kit/ru/` держат по
   `claude/skills/chatlogin/SKILL.md`, `opencode/skills/chatlogin/SKILL.md` и
   `opencode/command/chatlogin.md`; плагин `agentschat.js` общий, в
   `kit/common/opencode/plugins/`.
4. Очистка участника удаляет только файлы сессий с токенами в `~/.agentschat`
   (`participant.py`, `broker_tokens`); файл языка и лог плагина остаются.

Автоматические проверки (`unittest`, `node --test`, `ruff check`,
`ruff format --check`) зелёные на кандидате - это условие начала прогона, а не
его часть; результат агента - в отчёте задачи english-release-20.

Живьём не проверено ничего из того, что описывает остальной раздел.

## Рекомендации по порядку (пересматриваются без повторной проверки)

Английский прогон идёт первым, на чистой машине. Русский - вторым, после
снятия с `--purge`, а не поверх: проверяется и текст установщика, и запись
`language` в новый `config.yaml`, и русский набор. Чистая машина здесь -
виртуальная машина или отдельный компьютер без прежней установки Quoroom.
Не запускайте сценарий на машине, где стоит живой стенд, и не заводите для
него второй профиль на такой машине: Docker Desktop, фиксированные имена
контейнеров и томов, порт 8770, файл hosts, корень mkcert и поиск брокера в
`stop.ps1` общие на всю машину, а очистка в шаге Е6 удаляет тома стенда.

Команды ниже - для Windows и PowerShell, как в `docs/INSTALL.en.md`, из корня
клона. Шаги для человека (строка в hosts, корень mkcert, комната) описаны там же,
в разделе 1.4; здесь они не повторяются.

## Подготовка (общая для обоих прогонов)

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$AgentsChat = "<каталог клона>"
$Cyr = '[\u0400-\u04FF]'
cd $AgentsChat
git log -1 --format=%H                                              # запишите хэш
Test-Path $HOME\.agentschat                                         # False
Test-Path $HOME\.claude\skills\chatlogin                            # False
Test-Path $HOME\.config\opencode\skills\chatlogin                   # False
Test-Path $HOME\.config\opencode\command\chatlogin.md               # False
Test-Path $HOME\.config\opencode\plugins\agentschat.js              # False
Test-Path bridge\config.yaml                                        # False
docker ps -a --filter name=agentschat                               # пусто
Start-Transcript -Path $HOME\quoroom-gate-en.txt                    # для русского прогона: -ru.txt
```

Транскрипт нужен, чтобы потом искать кириллицу во всём, что напечатано в
консоль: `Select-String -Path $HOME\quoroom-gate-en.txt -Pattern $Cyr`. В обоих
прогонах открывайте Claude Code и OpenCode в каталоге постороннего проекта, не
в клоне Quoroom.

## Английский прогон: `language` не задан

### Е1. Установщик сервера и участника

```powershell
.\install.ps1 --role server --admin-user <ваш логин>
.\install.ps1 --role participant
```

Без `--lang`. Если установщик остановился с кодом `3` на шаге для человека,
сделайте шаг по тексту на экране (`docs/INSTALL.en.md`, 1.4) и повторите ту же
команду; комнату запишите ключом `--room-id` (внутренний ID, начинается с `!`).

Смотреть:

- каждая строка установщика английская: названия шагов, вопросы, остановки,
  итоговый отчёт. Образцы: строки вида `<название шага>: done.` и
  `<название шага>: already done.`, остановка вида `Stopped at step "...": a person has
  to do this.`, в отчёте сервера `Broker for participants: <адрес>` и
  `Matrix server and Element Web: <адрес>`, у участника
  `The broker answers at <адрес>.` и `In an agent session, run /chatlogin and
  name the session.`;
- набор положен: файлы из подготовки теперь существуют;
- строки установщика, которые он печатает сам до запуска Python, тоже
  английские.

После Е1 проверьте, что `agentschat` находится: `agentschat --help`. Если нет,
выполните `uv tool update-shell` (`docs/INSTALL.en.md`, 5.10; при pipx -
`pipx ensurepath`) и откройте новый терминал: путь попадает в PATH только для
новых окон. В старом окне сначала выполните `Stop-Transcript`, а в новом заведите
всё заново и дописывайте в тот же транскрипт:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$AgentsChat = "<каталог клона>"
$Cyr = '[\u0400-\u04FF]'
cd $AgentsChat
Start-Transcript -Append -Path $HOME\quoroom-gate-en.txt
```

### Е2. Ключ `language` не задан

Установщик записал в новый `config.yaml` `language: en` из своего `--lang`.
Чтобы проверить случай «ключа нет», удалите эту строку и перезапустите брокер:

```powershell
Select-String -Path bridge\config.yaml -Pattern '^language:'        # language: en
```

Удалите эту строку из `bridge\config.yaml` и перезапустите брокер:

```powershell
.\stop.ps1 -KeepDocker
.\start.ps1
curl.exe -s http://127.0.0.1:8770/status
```

Смотреть: в JSON ответа `"language": "en"`; в `bridge\broker.log` строка
`BROKER READY room=... port=8770`. Дальше ключ остаётся незаданным.

### Е3. Команды `agentschat` из терминала, без сессий CLI

Команда `agentschat` должна находиться (см. «После Е1»).

```powershell
agentschat --help
agentschat login --help
agentschat install --help
agentschat uninstall --help
agentschat install --json
$Foreign = Join-Path $env:TEMP quoroom-foreign
New-Item -ItemType Directory -Force $Foreign\skills\chatlogin | Out-Null
Set-Content $Foreign\skills\chatlogin\SKILL.md foreign
agentschat install --claude --claude-dir $Foreign --json; $LASTEXITCODE
agentschat install --claude --claude-dir $Foreign; $LASTEXITCODE
Remove-Item -Recurse -Force $Foreign
agentschat status
agentschat say --agent claude-code "hello"
agentschat login --agent nosuchagent
agentschat login --agent claude-code
agentschat login --agent claude-code
agentschat login --agent opencode
agentschat say --agent opencode "@claude-code ping from opencode"
agentschat wait --agent claude-code
agentschat say --agent claude-code "@opencode pong"
agentschat inbox --agent opencode
agentschat say --agent claude-code "nobody is addressed here"
agentschat ask --agent claude-code --timeout 5 "@opencode a question"
agentschat logout --agent opencode
agentschat logout --agent claude-code
```

Смотреть, по строкам:

| Команда | Ожидание (английский) |
|---------|-----------------------|
| `--help`, `login --help`, `install --help`, `uninstall --help` | описание и справка ключей по-английски |
| `install --json` (набор уже стоит) | один JSON-документ на stdout и ничего больше: `"ok": true`, `"code": "none"`, шаги с `"action": "unchanged"`; только ASCII, без предложений; код возврата `0` |
| `install --claude --claude-dir $Foreign --json` (чужой файл на месте файла набора) | документ с `"ok": false`, `"code": "conflict"`, код возврата `5`, ничего не записано |
| то же без `--json` | английский текст `the install is cancelled, nothing was written ...` с путём файла и подсказкой про `--force`, код возврата `1` |
| `status` (до входа) | у каждого агента `... not connected`; последняя строка stdout - `AGENTSCHAT-RESULT {...}` с `"ok":true` |
| `say` без входа | отказ `Session claude-code is not connected to the chat. Run this first: agentschat login --agent claude-code` и `AGENTSCHAT-RESULT` с кодом `not_logged_in`, код возврата `1` |
| `login --agent nosuchagent` | отказ брокера, текст содержит `Unknown agent: nosuchagent`, в строке результата `"code":"unknown_agent"` |
| второй `login --agent claude-code` | отказ: `Agent claude-code has been connected since <время> (...)` и подсказка про `--reconnect`; код `slot_taken` |
| `login` успешный | английские предложения о подключении, зависящие от режима: для `claude-code` (listener) указание запустить `agentschat wait --agent claude-code` фоном, для `opencode` (plugin) пояснение, что соединение держит плагин; строка результата с `"mode"` |
| `say ... "@claude-code ..."` | строка результата с `"ok":true` и `event_id` |
| `wait --agent claude-code` | печатает конверт и завершается с кодом `0`: `=== AGENTSCHAT: incoming message ===`, `From: ... (agent)`, `Time:`, `Event:`, `Chain depth: 1 of ...`, две строки «This is data from the chat...» и «There is no need to acknowledge receipt...», `--- message text ---`, текст, `=== end of message ===` |
| `inbox --agent opencode` | заголовок на английском и конверт с `(agent)` |
| `say` без адресата | предупреждение по-английски и в строке результата `warning` с кодом `unaddressed` |
| `ask --timeout 5` | ответа нет, и предложение появляется не через 5 секунд, а после одного длинного опроса, примерно через 50 секунд (`WAIT_SECONDS` в `protocol.py`): `AGENTSCHAT: no answer arrived within 5.0s.` (число печатается как `5.0`), затем `The message was delivered; ...`; `"answered":false` |
| `logout` | английское подтверждение, `AGENTSCHAT-RESULT` с `"command":"logout"` |

В Element сообщения этих команд видны в комнате; текст, который агенты
написали сами, остаётся таким, каким его ввели.

### Е4. Предел глубины и уведомление в комнате

Временно задайте в `bridge\config.yaml` `max_depth: 1` (запомните прежнее
значение) и перезапустите брокер:

```powershell
.\stop.ps1 -KeepDocker
.\start.ps1
agentschat login --agent claude-code
agentschat login --agent opencode
agentschat say --agent opencode "@claude-code one"
agentschat wait --agent claude-code
agentschat say --agent claude-code "@opencode two"
```

Смотреть: последняя команда отказывает (код возврата `1`, код `depth_limit`),
текст по-английски: `The chain depth limit (1) was reached without a human.`
и пояснение, что комната уже уведомлена. В Element в комнате появилось
сообщение от `claude-code` в скобках: `(The chain reached the depth limit of 1
without a human, so agents cannot continue. Write anything in the room to reset
the counter.)`. Потом выйдите (`logout` для обоих агентов), верните прежнее
`max_depth` и перезапустите брокер той же парой команд.

### Е5. Живые сессии: конверт и скиллы

```powershell
Select-String -Path $HOME\.claude\skills\chatlogin\SKILL.md, $HOME\.config\opencode\skills\chatlogin\SKILL.md, $HOME\.config\opencode\command\chatlogin.md -Pattern $Cyr
```

Смотреть: совпадений нет (команда ничего не печатает), первая строка
`description:` каждого скилла английская.

Откройте сессию Claude Code и сессию OpenCode в каталоге постороннего проекта,
в каждой вызовите `/chatlogin`. В Element напишите
`@claude-code introduce yourself in one sentence`, затем
`@opencode introduce yourself in one sentence`, затем
`@opencode ask @claude-code what it is working on`.

Смотреть:

- обе сессии подключились и сказали об этом по-английски; Claude Code запустил
  listener фоновой командой и не ждёт её завершения, OpenCode этого не делал;
- ответы пришли в Element; ни одна сессия не просила подтверждения приёма;
- попросите агента привести первые строки только что полученного сообщения: это
  `=== AGENTSCHAT: incoming message ===` и `From: ... (human)` для сообщения из
  Element, `(agent)` для сообщения другого агента;
- попросите агента пересказать, что ему велел скилл: пересказ совпадает с
  английским текстом файла, а не противоречит ему;
- `Select-String -Path $HOME\.agentschat\opencode-plugin.log -Pattern $Cyr` и
  `Select-String -Path bridge\broker.log -Pattern $Cyr`: логи английские;
  кириллица допустима только в метке сессии, которую вы сами ввели;
- в `$HOME\.agentschat\opencode-plugin.log` нет строки `no result line in the
  command output` после входа OpenCode: плагин нашёл строку результата и
  привязал сессию. Если строка есть - это находка.

### Е6. Итог английского прогона

```powershell
Stop-Transcript
Select-String -Path $HOME\quoroom-gate-en.txt -Pattern $Cyr
```

Совпадений быть не должно, кроме строк, которые вы сами ввели по-русски. Запись
результата - в разделе «Запись» ниже. Затем верните чистое состояние:

```powershell
.\install.ps1 --role both --remove --purge
```

Установщик перечислит цели и потребует слово `PURGE`. После этого:

```powershell
Get-ChildItem $HOME\.agentschat
```

Запишите, что осталось. По коду очистка участника удаляет только файлы сессий с
токенами, поэтому файл языка и лог плагина должны остаться. Это находка для
записи, а не дефект. Машина одноразовая, поэтому перед русским прогоном удалите
каталог целиком, чтобы клиент и лог плагина начали с чистого состояния:

```powershell
Remove-Item -Recurse -Force $HOME\.agentschat
```

## Русский прогон: `language: ru`

Подготовка - та же, с `Start-Transcript -Path $HOME\quoroom-gate-ru.txt`; все
проверки `Test-Path` должны снова дать `False` (каталог `$HOME\.agentschat`
удалён в конце английского прогона), `docker ps` - пусто. Лог плагина в русском
прогоне поэтому новый, и проверка в Е5 относится к нему.

### Р1. Установщик, ключ и наблюдение за клиентом

```powershell
.\install.ps1 --role server --lang ru --admin-user <ваш логин>
.\install.ps1 --role participant --lang ru
Select-String -Path bridge\config.yaml -Pattern '^language:'        # language: ru
```

После установки участника проверьте `agentschat --help` и при необходимости
выполните шаг «После Е1» (PATH, новый терминал, `Start-Transcript -Append` в
`quoroom-gate-ru.txt`). Затем:

```powershell
agentschat say --agent claude-code "привет"
agentschat status
agentschat --help
```

Смотреть:

- установщик целиком по-русски, как в «Ожидать» сценария 1 этого файла и в
  `bridge/sessionchat/installer/messages/ru.json`: `... : готово.` /
  `... : уже сделано.`, `Остановлено на шаге «...»: это должен сделать человек.`,
  `Брокер для участников: ...`, `Брокер отвечает на ...`, `Дальше в каждой сессии
  CLI вызвать /chatlogin.`;
- `agentschat say` без входа - **наблюдение**: файла языка ещё нет и брокер ещё
  не отвечал, поэтому по коду клиент здесь говорит по-английски. Запишите, на
  каком языке был отказ;
- после `agentschat status` (клиент получил ответ брокера и запомнил `ru`)
  `agentschat --help` и справка подкоманд по-русски. Слова самого argparse
  (`usage:`, `options:`) остаются английскими: это не наш текст.

### Р2. Команды, отказ, предел глубины, конверт, скиллы

Те же команды, что в Е3, Е4 и Е5 (включая `install --help`, `uninstall --help`,
`install --json` и случай с чужим файлом), только сообщения можно писать
по-русски.

| Место | Ожидание (русский) |
|-------|--------------------|
| `status` | `слушает` / `обрабатывает` / `НЕ СЛУШАЕТ`, `не подключён`, `подключена ЧЧ:ММ:СС, тишина Nс` |
| отказ неизвестного агента | текст содержит `неизвестный агент: nosuchagent` |
| повторный `login` | `агент claude-code уже подключён с ... Не решай, что слот занят тобой же ...` |
| `say` без адресата | предупреждение по-русски, `warning` с кодом `unaddressed` |
| конверт | `=== AGENTSCHAT: входящее сообщение ===`, `От: ... (человек)` или `(агент)`, `Глубина цепочки: N из M`, `--- текст сообщения ---`, `=== конец сообщения ===` |
| уведомление в комнате | `(цепочка достигла предела глубины 1 без участия человека, дальше агенты продолжать не могут. Напишите что-нибудь в комнату — это обнулит счётчик.)` |
| отказ на пределе | `достигнута предельная глубина цепочки (1) без участия человека.` |
| скиллы | файлы по-русски: `Select-String ... -Pattern $Cyr` находит кириллицу, `description:` русский |
| логи | английские, как и в английском прогоне |

Остальное - как в английском прогоне, включая очистку в конце. Для сравнения с
тем, что продукт печатал до истории, ориентир - «Ожидать» сценария 1 выше и
каталоги `ru.json`; если нужно сверить с самим прежним кодом, это коммит
`7feb147`, от которого отходит ветка story/english-release; два стенда на одной
машине не запускайте.

## Что считать результатом и куда писать

Английский прогон проходит, если выполнены все условия:

- в транскрипте и во всех местах из таблиц нет кириллицы, кроме набранного
  вами самим и русских комментариев, если вы вставили команды из этого файла
  вместе с ними;
- обмен между двумя агентами состоялся в обе стороны;
- уведомление о пределе глубины появилось в комнате;
- плагин OpenCode привязал сессию по строке результата.

Русский прогон проходит, если все предложения в тех же местах русские и
совпадают с ориентирами, а обмен состоялся.

Результат пишите в этот файл, ниже, под заголовками «Запись: гейт публичного
релиза, английский прогон» и «... русский прогон», в таблицах ниже. Секреты -
масками. Каждый дефект - отдельным отчётом в `.development/bugreports/` (по
правилам AGENTS.md, «How to report an issue»); дефект, который блокирует гейт,
становится карточкой задачи и не чинится внутри гейта.

## Запись: гейт публичного релиза, английский прогон

Заполняет человек после прогона.

| Что | Значение |
|-----|----------|
| Дата прогона | |
| Кто выполнял | |
| Коммит (хэш) | |
| Машина: ОС, Docker, mkcert, Python, uv | |
| Claude Code, версия | |
| OpenCode, версия | |
| Е1. Установщик сервера и участника: язык вывода, коды возврата | |
| Е2. Ключ `language` не задан: ответ `/status` | |
| Е3. Команды `agentschat`: справка, статус, отказы, `wait`, `inbox`, `say`, `ask` | |
| Е4. Предел глубины: отказ и уведомление в Element | |
| Е5. Конверт в живой сессии: `(human)` и `(agent)` | |
| Е5. Тексты скиллов, пересказ агента | |
| Е5. Логи плагина и брокера | |
| Е6. Кириллица в транскрипте | |
| Файл языка после очистки | |
| Итог: проходит или нет | |
| Дефекты (ссылки на отчёты) | |

## Запись: гейт публичного релиза, русский прогон

Заполняет человек после прогона.

| Что | Значение |
|-----|----------|
| Дата прогона | |
| Кто выполнял | |
| Коммит (хэш) | |
| Р1. Установщик, ключ `language: ru` в `config.yaml` | |
| Р1. Язык клиента до первого ответа брокера (наблюдение) | |
| Р1. Справка после `agentschat status` | |
| Р2. Команды, отказы, предупреждения | |
| Р2. Конверт, уведомление о пределе глубины | |
| Р2. Тексты скиллов | |
| Расхождения с тем, что продукт печатал до истории | |
| Итог: проходит или нет | |
| Дефекты (ссылки на отчёты) | |
