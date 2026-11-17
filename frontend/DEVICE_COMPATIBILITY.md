# Device compatibility

The app runs inside Telegram's WebView. Home-screen shortcuts require Telegram
Bot API 8.0 support; a successful API call only starts the native installation
flow. Only an `added` status or `homeScreenAdded` event confirms installation.
Telegram can return `unknown` or omit the event even after adding the icon.

The shared shortcut provider keeps the banner and Settings action in sync,
rechecks after an attempt and on return to the app, and offers retry guidance
when installation is not confirmed. It mounts after Telegram initialization.
On Xiaomi/Redmi, Telegram may need the phone's **Home screen shortcuts**
permission. The Mini App cannot grant this permission.

Device safe-area insets and Telegram content insets are combined on all four
edges. Missing device insets retain the browser's `env(safe-area-inset-*)`
fallback. The create button leaves at least 24 CSS pixels beyond its shadow and
the usable right/bottom edge; desktop placement follows the content column.

## Verification

Run from the repository root:

```sh
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend test
npm --prefix frontend run build
```

Browser layout checks use local fixture data at 320, 360, 390, 412, 768, and
1280 CSS-pixel widths, plus 800 × 360 landscape with simulated Telegram
insets. Check long usernames, the installation banner, the create button,
scrolling to the final bill, and scrolling within the create/help dialogs.
Width or user-agent emulation does not test an actual Android launcher or iOS
WebView.

Before release, check the actual Redmi inside Telegram: tap Add, respond to any
native prompt, inspect the launcher, and return to the app. Repeat with shortcut
permission disabled/enabled, and with gesture/button navigation and rotation.
Also check a supported iPhone and another Android device. Record OS, Telegram,
and Android System WebView versions with any failure.

Tailwind 4's documented browser baseline is Chrome 111+, Safari 16.4+, and
Firefox 128+. These changes do not extend that framework baseline.

References: [Telegram Mini Apps](https://core.telegram.org/bots/webapps),
[Xiaomi app permissions](https://www.mi.com/uk/support/faq/details/KA-497759/),
[Tailwind browser support](https://tailwindcss.com/docs/compatibility).
