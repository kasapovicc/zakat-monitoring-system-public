# Zakat Nisab Monitoring System

An automated system that monitors ProCredit Bank statements via Gmail, tracks balances across multiple currencies and sources, and determines zakat eligibility based on Islamic nisab requirements.

Available in two modes:
- **macOS desktop app** — menubar app with setup wizard, dashboard, and local encrypted config
- **GitHub Actions script** — runs monthly, sends email reports (zero maintenance)

> **Disclaimer**: This system is for informational purposes only. Users are responsible for verifying all calculations and consulting qualified Islamic scholars for final zakat determinations.

---

## Why This Exists

Zakat calculation requires tracking whether your assets remain above the nisab threshold for 12 consecutive Hijri (lunar) months. This system automates:

- Monthly balance tracking from bank statements
- Hijri calendar date conversion
- Historical balance storage (encrypted)
- Automatic zakat eligibility determination
- Email notifications when zakat becomes due

This removes the manual burden of downloading statements, converting dates, and tracking months manually.

---

## What It Does

1. **Automated Email Processing** — connects to Gmail, finds ProCredit Bank statement emails, downloads and parses PDF attachments
2. **Multi-Account & Multi-Source Support** — personal and company BAM/EUR accounts, automatic EUR to BAM conversion
3. **Islamic Compliance Tracking** — Hijri calendar conversion, consecutive month tracking, nisab threshold checks, 2.5% zakat calculation
4. **Secure Storage & Reporting** — encrypted balance history, HTML email reports with progress tracking, sensitive data masked in logs

---

## macOS Desktop App

Download `Zekat.app` from the [GitHub Releases](https://github.com/kasapovicc/zekat-monitoring-system-public/releases) page. No Python or dependencies required — the app is self-contained.

If macOS blocks the app, right-click it and select **Open**, or run `xattr -cr Zekat.app` in Terminal.

### Features

- **Menubar app** — lives in your macOS menu bar, no Dock icon
- **Setup wizard** — 5-step guided configuration (email sources, accounts, delivery, review)
- **Dashboard** — view current balances, nisab progress, and zakat status
- **Settings** — manage email sources, year progress, and restart setup
- **History** — browse past analysis results
- **Scheduled runs** — built-in scheduler runs analysis monthly

---

## GitHub Actions Script

Runs automatically on the first Monday of each month via GitHub Actions. No local installation needed — just configure secrets in your fork and it runs in the cloud.

- Monthly automated runs with email report delivery
- Manual triggering via workflow dispatch
- Encrypted history committed to the repository

---

## Getting Started

### macOS App

1. Download `Zekat.app` from [GitHub Releases](https://github.com/kasapovicc/zekat-monitoring-system-public/releases)
2. Open the app — the setup wizard will guide you through configuration

### GitHub Actions

1. Fork this repository
2. Configure GitHub Secrets
3. Enable GitHub Actions

**See [docs/setup.md](docs/setup.md)** for detailed instructions, Gmail App Password setup, building from source, troubleshooting, and more.

---

## Email Report Example

```
ZAKAT NISAB ANALYSIS REPORT
Generated: 01.11.2025 at 09:15:32

MULTI-ACCOUNT BALANCES
BAM Account (****0142): 5,234.50 BAM
EUR Account (****1209): 1,250.75 EUR
EUR to BAM: 1,250.75 x 1.95583 = 2,446.22 BAM

TOTAL ASSETS
Combined Balance: 7,680.72 BAM
Additional Assets: + 8,000.00 BAM
TOTAL: 15,680.72 BAM

NISAB ANALYSIS
Threshold: 24,654.00 BAM
Above Nisab: NO
Consecutive Months: 8/12
[--------____] 67% complete

ZAKAT CALCULATION
Zakat Due: NO
Amount: 0.00 BAM
```

---

## Known Limitations

- **Bank support** — ProCredit Bank Bosnia only (other banks require adding PDF parsing patterns)
- **Email provider** — Gmail via IMAP only
- **Nisab fetch** — zekat.ba loads values via JavaScript, so the system uses a fallback value that should be updated quarterly
- **Exchange rate** — EUR/BAM rate is hardcoded at 1.955830 (Bosnia's currency is pegged to EUR)

---

## Security & Privacy

- **Encrypted storage** — balance history encrypted with Fernet; app config encrypted with Argon2id + Fernet
- **GitHub Secrets** — all credentials stored securely (script mode)
- **Data masking** — account numbers, balances, emails masked in logs
- **TLS encryption** — email reports sent via STARTTLS
- **App passwords** — Gmail integration uses app-specific passwords

---

## Contributing

Contributions welcome! Please:

1. Check existing issues first
2. Fork the repository
3. Create feature branch
4. Submit pull request with clear description

---

## License

MIT License - see [LICENSE](LICENSE) file

---

## Important Disclaimer

**This system is for informational purposes only.**

- **Verify all calculations independently**
- **Consult qualified Islamic scholars** for final zakat determinations
- **Check zekat.ba** for current official nisab values
- **This tool assists with tracking** but does not replace proper Islamic guidance

The developers are not responsible for any financial or religious decisions made based on this system's output.
