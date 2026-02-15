# Split The Bill 🧾💨

**Split The Bill** is a modern Telegram Mini App (TMA) designed for easy bill sharing in restaurants and cafes. It features a unique "notebook" aesthetic and a robust backend to track items, participants, and payments.

## 🌟 Key Features

- **Telegram Integration**: Seamless login and sharing within Telegram.
- **Notebook Design**: Beautiful yellow paper aesthetic with handwritten fonts (`Caveat`).
- **Dynamic Bill Management**: Create bills, add items, and manage participants.
- **Payment Tracking**: Monitor who has paid their share in real-time.
- **Dark Mode**: "Aged paper" theme for low-light environments.
- **Multi-language**: Support for English, Russian, and Uzbek.

## 🏗 Project Structure

The project is structured as a monorepo:

- [**`backend/`**](file:///home/leonid/projects/split-the-bill/backend): FastAPI application with PostgreSQL database.
- [**`frontend/`**](file:///home/leonid/projects/split-the-bill/frontend): Next.js App Router application using Tailwind CSS 4.
- [**`nginx/`**](file:///home/leonid/projects/split-the-bill/nginx): Configuration for Nginx reverse proxy (Development & Production).
- [**`docker-compose.yml`**](file:///home/leonid/projects/split-the-bill/docker-compose.yml): Multi-container orchestration.
- [**`Makefile`**](file:///home/leonid/projects/split-the-bill/Makefile): Useful commands for development.

## 🛠 Tech Stack

### Backend

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **ORM**: [SQLModel](https://sqlmodel.tiangolo.com/)
- **Database**: [PostgreSQL](https://www.postgresql.org/) (Docker) / [SQLite](https://www.sqlite.org/) (Local dev option)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)

### Frontend

- **Framework**: [Next.js 15+](https://nextjs.org/) (App Router)
- **Styling**: [Tailwind CSS 4](https://tailwindcss.com/)
- **State Management**: [Zustand](https://github.com/pmndrs/zustand)
- **Animations**: [Framer Motion](https://www.framer.com/motion/)
- **Telegram SDK**: [@telegram-apps/sdk](https://github.com/telegram-apps/sdk)

### Infrastructure

- **Proxy**: [Nginx](https://www.nginx.com/)
- **Containerization**: [Docker](https://www.docker.com/) & Docker Compose
- **Tunneling**: [Cloudflared](https://github.com/cloudflare/cloudflared) (for production TMA testing)

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- `make` (optional, but recommended)

### Running with Docker

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd split-the-bill
   ```

2. **Configure environment Variables**:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in the required tokens (e.g., `TG_TOKEN`, `CLOUDFLARE_TUNNEL_TOKEN`).

3. **Start the application**:
   ```bash
   make docker-up
   # OR
   docker compose --profile dev up --build -d
   ```

The application will be available at:

- **Frontend**: `http://localhost:80` (Proxied via Nginx)
- **Backend API**: `http://localhost:80/api`
- **Swagger Docs**: `http://localhost:80/api/docs`

## 🛠 Development Workflow

Common commands using the [**`Makefile`**](file:///home/leonid/projects/split-the-bill/Makefile):

| Command                                | Description                                 |
| -------------------------------------- | ------------------------------------------- |
| `make docker-up`                       | Build and start containers in detached mode |
| `make docker-down`                     | Stop and remove containers                  |
| `make docker-logs`                     | Follow logs from all containers             |
| `make docker-logs-backend`             | Follow backend logs                         |
| `make db-migrate msg="migration_name"` | Generate a new Alembic migration            |
| `make db-upgrade`                      | Apply database migrations                   |
| `make test-backend`                    | Run backend tests using Pytest              |

## 🌎 Localization

The application supports English, Russian, and Uzbek languages. Look into `frontend/src/locales` for translation files.

---

Built with ❤️ for Telegram Mini Apps enthusiasts.
