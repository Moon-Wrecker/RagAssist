# Run the stack locally

**Type:** Tutorial · **Audience:** a developer who sees RagAssist for the first time · **Verified against:** `a989287`

**In plain English:** In this lesson you start the whole RagAssist system on your own computer. You make a settings
file, start the containers and open the web app. At the end the web app shows a sign-in page and the health check says
`ok`. You do not need to know the code.

This lesson is the first of five. The next lesson is
[create a workspace and sign in](02-create-a-workspace-and-sign-in.md).

## What you will build

You will run seven parts on your computer. Docker runs them. The table shows each part and its job.

| Part | Its job |
|---|---|
| `postgres` | Stores all data, including the vectors for search |
| `localstack` | Pretends to be Amazon S3 and Amazon SQS on your computer |
| `mock-saas` | Pretends to be a customer billing system |
| `migrate` | Creates the database tables, then stops |
| `api` | The HTTP and live-event server |
| `worker` | Reads uploaded files and builds the search index |
| `web` | The web page and a proxy to the API |

The optional `redis` part is off. You do not need it. For the full picture, read
[the container diagram](../c4/02-containers.md). The [glossary](../glossary.md) explains each project term.

## Before you start

You need these items:

- Python 3.12 (the project needs 3.12 and below 3.13).
- [uv](https://docs.astral.sh/uv/), the Python package tool.
- Docker Desktop or Docker Engine with the `docker compose` command.
- An API key for one model provider. This lesson uses OpenAI, because the default search embeddings need it.
- A copy of the repository on your computer.

> **NOTE.** The key is a secret. You will put it in the file `.env` only. Git ignores that file. Never write the key in
> a document, a test or a commit message.

## Steps

1. Open a terminal in the root folder of the repository.
2. Create a virtual environment and install the project:

   ```bash
   uv venv
   uv pip install -e ".[dev]"
   ```

3. Activate the virtual environment. On Windows PowerShell run `.venv\Scripts\Activate.ps1`. On Linux and macOS run
   `source .venv/bin/activate`.
4. Make the settings file:

   ```bash
   ragassist init-env
   ```

   The command writes `.env` and prints the names of the values that it made. It does not print the values.

   > **CAUTION.** If `.env` already exists, the command stops with exit code 1. Do not add `--force` yet. The option
   > replaces the file with no backup. It makes new database passwords, and an old database volume then rejects them.

5. Open `.env` in your editor.
6. Find the line `OPENAI_API_KEY=`. Paste your own key after the equal sign. Save the file.
7. Find the line `WEB_BASE_URL=`. Change it to `http://localhost:<WEB_PORT>`. Replace `<WEB_PORT>` with the number
   that is on the line `WEB_PORT=` in the same file.

   The web app and the API compare the browser `Origin` header with this value. The scheme, the host and the port must
   match exactly. The template value is for the Vite development server, not for the container.

8. Start everything:

   ```bash
   docker compose up -d --build
   ```

   The first build takes several minutes. The command ends when all parts have started.

9. Look at the state of the parts:

   ```bash
   docker compose ps
   ```

   `postgres`, `localstack`, `mock-saas`, `api` and `web` show `healthy` after a short time. `migrate` shows
   `exited (0)`. That is correct: it runs once and stops. `worker` shows `running`.

10. Open `http://localhost:<WEB_PORT>/healthz` in your browser. Use your number for `<WEB_PORT>`.
11. Read the answer. It is `{"status":"ok","app":"RagAssist"}`.
12. Open `http://localhost:<WEB_PORT>/` in your browser. The page shows the sign-in form with the fields Workspace,
    Email and Password.

## Check

You are done when both of these are true:

- `docker compose ps` shows no part in the state `unhealthy` or `restarting`.
- The browser shows the sign-in form. You cannot sign in yet. You have no account. Lesson 2 makes one.

## If something is wrong

- The command `ragassist` is not found. Use `python -m ragassist.cli.main init-env`, or activate the virtual
  environment. See [the command-line reference](../reference/cli.md).
- A part stops with a message that starts with `15-web-env:`. The `web` container checks `WEB_PORT`, `WEB_SERVER_NAME`
  and `WEB_API_UPSTREAM`. See [troubleshoot common problems](../how-to/troubleshoot-common-problems.md).
- The build fails at the `seed/` folder. The file `infra/docker/api.Dockerfile` copies `seed/`, and that folder is not
  in git at this commit. A clean build can fail. See the troubleshooting page.
- `docker compose up` says `run ragassist init-env`. A required value is missing from `.env`. Run step 4 again.

## Clean up

Leave the stack running for the next lesson. To stop it later, run `docker compose down`. That keeps your data. The
command `docker compose down -v` deletes the data volumes. Use it only when you want a fresh start.

## Next step

Go on to [create a workspace and sign in](02-create-a-workspace-and-sign-in.md).

Unverified: the author did not run these steps against a live stack. The commands follow the code, the compose file and
the template `.env.example` at this commit.
