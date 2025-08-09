<p align="center">
  <img src="https://framerusercontent.com/images/dITUuTk8cKrr6KBrjwv9142LXLw.png" width="120" alt="legacy-use logo" />
  <h3 align="center">🚀  Turn any legacy application into a modern REST API, powered by AI.</h3>
</p>

# Contributing to legacy-use

First off, thanks for taking the time to make legacy-use even better! ❤️

The best ways to get involved:

- Create and comment on [issues](https://github.com/legacy-use/legacy-use/issues)
- Open a pull request—big or small, we love them all.

We welcome contributions through GitHub pull requests. This document outlines our conventions regarding development workflow, commit message formatting, contact points, and other resources. Our goal is to simplify the process and ensure that your contributions are easily accepted.

## Project Structure

### Tech Stack

- [React](https://react.dev/)
- [Vite](https://vitejs.dev/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Docker](https://www.docker.com/)
- [PostHog](https://posthog.com/)
- [Sentry](https://sentry.io/)

### Terminology

- Target - A target is a machine that you want to automate. It can be any computer that you can access via remote access software.
- Session - A session is a hosted connection between the target and the server. It is used to run jobs on the target.
- API - An API is a pre-defined set of instructions on how to execute a job on the target. It can include multiple steps, parameters, cleanup steps, etc.
- Job - A job is a single execution of an API on the target and works exactly like a REST endpoint. One can forward the needed parameters to the job, and the job will execute the API on the target.
- Tools - Modular helpers that enable the agent to interact with the target and external systems.

### Architecture

- The first thing you'll touch is our React-based frontend. With it you can set up targets, create API endpoints, and inspect running or past jobs.
- Our FastAPI server powers the frontend and, more importantly, acts as the gateway between you and the machines you want to automate. Once a target is set up and a Session created, the server spins up a Docker container that hosts that session solely for the target.
- Flow of a call:
    - One sends a POST request to the /targets/{target_id}/jobs/ endpoint.
    - The server will then spin up a Docker container that hosts the session, creating and maintaining a connection to the target.
    - The server adds the job to the target-specific job queue and returns a job ID.
        - Once the job leaves the queue it runs asynchronously, navigating the target machine.
        - The agent will iteratively take screenshots of the target, walk through the steps of the API, and make use of the different tools available to it, in order to execute the specified API job.
    - After completion, the agent sends the results back to the server, written to the database and marked as successful.

### Repository Structure

- [app](./app)

- [server](./server)
    - Have a look at the [core.py](./server/core.py) file to get an overview of the flow of a call.
    - Have a look at the [sampling_loop.py](./server/computer_use/sampling_loop.py) file to get an overview of the agentic loop.

- [infra](./infra)

## Getting setup for development

Following the steps in the [README.md](./README.md) file will get you up and running with the project, but if you want to get more in depth, here are some tips:

### Local development cheatsheet

#### Backend (FastAPI)

1. **Install [uv](https://github.com/astral-sh/uv)** – a super-fast drop-in replacement for `pip`/`virtualenv`.

   *macOS*
   ```bash
   brew install uv
   ```
   *Linux / WSL / other*
   ```bash
   curl -Ls https://astral.sh/uv/install.sh | sh
   ```

2. **Create & activate a virtual-environment** in the project root:
   ```bash
   cd legacy-use   # repo root
   uv venv              # creates .venv using the current Python
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install Python dependencies** defined in `pyproject.toml`:
   ```bash
   uv pip install -r pyproject.toml        # core deps
   uv pip install --group dev -r pyproject.toml  # dev/test/lint extras
   uv run pre-commit instal   # install pre-commit
   ```

4. **Run the API with hot-reload**:
   ```bash
   uvicorn server.server:app --host 0.0.0.0 --port 8088 --reload
   ```
   Open http://localhost:8088/redoc to confirm everything is up.

#### Frontend (React + Vite)

1. **Install Node.js (≥20) or [Bun](https://bun.sh/):**
   ```bash
   # macOS example
   brew install node        # or: brew install bun
   ```

2. **Install JS dependencies:**
   ```bash
   pnpm install
   ```

3. **Start the Vite dev server (hot-reload):**
   ```bash
   pnpm run dev
   ```
   Visit http://localhost:5173 and start hacking!

## Contact us via Discord

We have a dedicated Discord server for contributors and users. You can join it [here](https://link.browser-use.com/discord).
