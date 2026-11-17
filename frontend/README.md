# Split The Bill - Frontend

A Next.js frontend for the Split The Bill Telegram mini app with notebook-style design.

## Features

- 📝 **Create Bills**: Create bills with items and participants
- 👥 **Manage Participants**: Add participants manually or via invite links
- 💰 **Split Costs**: Assign items to participants or split evenly
- ✅ **Track Payments**: Monitor who has paid and who hasn't
- 🎨 **Notebook Theme**: Beautiful yellow paper aesthetic with handwritten fonts
- 🌓 **Dark Mode**: Aged paper theme for dark mode
- 🌍 **Multi-language**: Support for English, Russian, and Uzbek
- 📱 **Telegram Integration**: Native Telegram Mini App experience

## Tech Stack

- **Framework**: Next.js 16+ with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS 4
- **Animations**: Framer Motion
- **State Management**: Zustand
- **API Client**: Axios
- **Form Validation**: React Hook Form + Zod
- **Icons**: Lucide React
- **Telegram**: @telegram-apps/sdk

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Backend API running (see `split-the-bill-backend` repository)

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd split-the-bill-frontend
```

2. Install dependencies:

```bash
npm install
```

3. Create `.env.local` file:

```bash
cp .env.example .env.local
```

4. Update `.env.local` with your configuration:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

5. Run the development server:

```bash
npm run dev
```

6. Open [http://localhost:3000](http://localhost:3000) in your browser.

## Project Structure

```
src/
├── app/                    # Next.js app router pages
│   ├── layout.tsx         # Root layout with Telegram provider
│   ├── page.tsx           # Dashboard page
│   └── globals.css        # Global styles with notebook theme
├── components/
│   ├── ui/                # Reusable UI components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Modal.tsx
│   │   └── CircleButton.tsx
│   ├── dashboard/         # Dashboard components
│   ├── bill/              # Bill-related components
│   └── layout/            # Layout components
├── lib/
│   ├── api/               # API client and functions
│   │   ├── client.ts
│   │   ├── bills.ts
│   │   └── users.ts
│   ├── telegram/          # Telegram SDK integration
│   │   └── init.ts
│   ├── store/             # Zustand store
│   │   └── useStore.ts
│   └── utils/             # Utility functions
│       ├── currency.ts
│       └── validation.ts
└── types/                 # TypeScript type definitions
    ├── api.ts
    └── telegram.ts
```

## Development

### Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint

### Design System

The app uses a notebook theme with the following color palette:

**Light Mode:**

- Background: `#fff9db` (yellow paper)
- Foreground: `#1a1a1a` (ink)
- Accent: `#ff8c42` (orange)

**Dark Mode:**

- Background: `#2a2419` (aged paper)
- Foreground: `#f5f5dc` (beige)
- Accent: `#ff8c42` (orange)

**Font:**

- Handwritten: Caveat

## Telegram Mini App Setup

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Enable Mini App in bot settings
3. Set the Mini App URL to your deployment URL

## Backend Integration

This frontend connects to the FastAPI backend. Make sure the backend is running and the `NEXT_PUBLIC_API_URL` is correctly set.

Backend repository: `split-the-bill-backend`

## Deployment

### Vercel (Recommended)

1. Push your code to GitHub
2. Import project in Vercel
3. Add environment variables
4. Deploy

### Other Platforms

Build the production bundle:

```bash
npm run build
```

Then deploy the `.next` folder to your hosting platform.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT

## Support

For issues and questions, please open an issue on GitHub.
