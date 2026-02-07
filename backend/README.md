# Split The Bill - Backend API

FastAPI backend for the "Split The Bill" Telegram Mini App.

## Overview

This is a backend API for managing split bills in restaurants and cafes. Users can create bills, add items, invite participants, and track payments.

## Features

- **User Management**: Create and manage users via Telegram authentication
- **Bill Management**: Create bills with total amounts and payment details
- **Item Tracking**: Add individual items to bills
- **Participant Management**: Add registered users or guests to bills
- **Payment Tracking**: Track who has paid their share

## Tech Stack

- **FastAPI**: Modern, fast web framework
- **SQLModel**: SQL database ORM with Pydantic integration
- **SQLite**: Lightweight database for MVP
- **Uvicorn**: ASGI server

## Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

## Running the Application

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`

## API Documentation

Once the server is running, visit:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## API Endpoints

### Users

- `POST /users/` - Create or update a user
- `GET /users/{user_id}` - Get user by ID

### Bills

- `POST /bills/` - Create a new bill
- `GET /bills/{bill_id}` - Get bill details with items and participants
- `POST /bills/{bill_id}/items` - Add an item to a bill
- `POST /bills/{bill_id}/participants` - Add a participant to a bill

## Database Schema

The application uses the following models:

- **User**: Telegram users
- **Bill**: Split bills with total amount and payment details
- **BillItem**: Individual items in a bill
- **BillUser**: Participants in a bill (users or guests)

All monetary values are stored as integers in the smallest currency unit (cents/kopeks) to avoid floating-point precision issues.

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application
│   ├── database.py       # Database configuration
│   ├── models.py         # SQLModel database models
│   └── routers/
│       ├── __init__.py
│       ├── users.py      # User endpoints
│       └── bills.py      # Bill endpoints
├── requirements.txt
└── README.md
```

## Development

The database file `split_the_bill.db` will be created automatically on first run.

## Next Steps

- Add authentication with Telegram Web App initData validation
- Implement WebSocket for real-time updates
- Add bill closing logic when all participants have paid
- Add participant payment confirmation endpoint
- Implement bill history filtering
