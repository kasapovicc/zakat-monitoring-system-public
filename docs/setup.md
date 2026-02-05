# Zakat Monitoring System - Setup Guide

Complete installation and configuration guide for setting up your own zakat monitoring system.

There are two ways to run this system:

| | GitHub Actions (Script) | macOS App |
|---|---|---|
| **Setup** | Fork repo, add GitHub Secrets | Download from Releases, use setup wizard |
| **Runs** | Monthly via cron, or manual dispatch | Monthly via built-in scheduler |
| **Config** | Environment variables / GitHub Secrets | Encrypted local file with UI |
| **Reports** | Email notifications | Dashboard + email notifications |
| **Best for** | Set-and-forget automation | Interactive use, multiple email sources |

> **Disclaimer**: This system is for informational purposes only. Users are responsible for verifying all calculations and consulting qualified Islamic scholars for final zakat determinations.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start: GitHub Actions](#quick-start-github-actions)
- [Quick Start: macOS App](#quick-start-macos-app)
- [Forking This Project](#forking-this-project)
- [GitHub Secrets Configuration](#github-secrets-configuration)
- [Gmail Setup](#gmail-setup)
- [Installation Steps](#installation-steps)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)
- [Building from Source](#building-from-source)
- [Technical Details](#technical-details)

---

## Prerequisites

### For the macOS App
- **macOS 12+**
- No other dependencies (self-contained app bundle)

### For GitHub Actions / Script Mode
- **Python 3.9 or higher**
- **Git** (for version control)
- **Internet connection** (for Gmail, nisab fetching)
- **GitHub account** (private repository recommended)

### Email Requirements
- **Gmail account** with App Password enabled
- **IMAP access** enabled in Gmail settings

### Bank Requirements
- **ProCredit Bank account(s)** in Bosnia and Herzegovina
- **Email statements enabled** (sent to Gmail account)
- Expected statement format: `account-number_YYYY-MM-DD.pdf`

---

## Quick Start: GitHub Actions

1. Fork this repository
2. Delete `zakat_history_encrypted.json` (you can't decrypt original author's data)
3. Generate encryption key (see [below](#generate-encryption-key))
4. Create Gmail App Password (see [below](#gmail-setup))
5. Configure GitHub Secrets (see [below](#github-secrets-configuration))
6. Enable GitHub Actions in your fork
7. Test with manual workflow run

## Quick Start: macOS App

1. Download the release zip from [GitHub Releases](https://github.com/kasapovicc/zekat-monitoring-system-public/releases) and unzip it
2. **Double-click `install-zekat.command`** — this clears the macOS quarantine flag and opens the app
3. If you skipped the install script: open `Zekat.app` manually, then go to **System Settings > Privacy & Security**, scroll down and click **"Open Anyway"**
4. The setup wizard walks you through configuring email sources, account numbers, and report delivery
5. Configuration is encrypted locally at `~/Library/Application Support/Zekat/config.enc`

To build from source or run in dev mode, see [Building from Source](#building-from-source) below.

---

## Forking This Project

If you want to use this system for your own zakat monitoring:

### Step 1: Fork the Repository

Click **Fork** button on GitHub to create your own copy.

**Important:** GitHub Secrets do NOT transfer with forks. You must configure your own.

### Step 2: Delete Encrypted History

```bash
# In your forked repo
git clone https://github.com/YOUR_USERNAME/zekat-monitoring-system.git
cd zekat-monitoring-system
git rm zakat_history_encrypted.json
git commit -m "Remove original author's encrypted history"
git push origin main
```

The workflow will create a fresh encrypted history file on first run.

### Step 3: Configure Your Fork

Follow the steps in [GitHub Secrets Configuration](#github-secrets-configuration) below.

---

## GitHub Secrets Configuration

**See [`.env.example`](../.env.example)** for a complete list of all variables with examples and quick setup commands.

Add these secrets in your repository: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

### Required Secrets

#### Email Configuration

| Secret | Description | Example |
|--------|-------------|---------|
| `EMAIL_USERNAME` | Gmail address | `your.email@gmail.com` |
| `EMAIL_PASSWORD` | Gmail App Password (NOT regular password) | `abcd efgh ijkl mnop` |
| `SENDER_EMAIL` | Email address for sending reports | `your.email@gmail.com` |
| `RECIPIENT_EMAIL` | Email address to receive reports | `your.email@gmail.com` |

#### Security Configuration

| Secret | Description |
|--------|-------------|
| `ZAKAT_ENCRYPTION_KEY` | Fernet encryption key for history storage |

Generate with:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

#### Account Configuration

| Secret | Description | Example |
|--------|-------------|---------|
| `BAM_ACCOUNT` | ProCredit BAM account number | `1941510380700142` |
| `EUR_ACCOUNT` | ProCredit EUR account number | `1941510380701209` |

#### Financial Configuration

| Secret | Description | Default |
|--------|-------------|---------|
| `ADDITIONAL_ASSETS` | Additional assets in BAM (cash, gold, savings, investments) | `0.00` |
| `NISAB_FALLBACK_BAM` | Fallback nisab value in BAM (update quarterly from zekat.ba) | `24624.0` |

#### Company Email Source (Optional)

For monitoring company bank accounts in addition to personal:

| Secret | Description |
|--------|-------------|
| `COMPANY_EMAIL_USERNAME` | Company Gmail address |
| `COMPANY_EMAIL_PASSWORD` | Company Gmail App Password |
| `COMPANY_BAM_ACCOUNT` | Company ProCredit BAM account number |
| `COMPANY_EUR_ACCOUNT` | Company ProCredit EUR account number |

**Note:** All 4 company variables must be set for the company source to activate. If any are missing, the system operates in single-source mode (personal accounts only).

---

## Gmail Setup

### Enable IMAP

1. Open Gmail settings (⚙️ → See all settings)
2. Go to **Forwarding and POP/IMAP** tab
3. Enable IMAP
4. Save changes

### Generate App Password

1. Go to **Google Account settings** → https://myaccount.google.com
2. Navigate to **Security** → **2-Step Verification**
3. Scroll to bottom → **App passwords**
4. Select app: **Mail**
5. Select device: **Other (Custom name)** → enter "Zakat Monitor"
6. Click **Generate**
7. Copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)
8. Add as `EMAIL_PASSWORD` secret in GitHub

**Note:** If you don't see "App passwords" option:
- Ensure 2-Step Verification is enabled
- You may need to use a security key or different 2FA method first

---

## Installation Steps

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/zekat-monitoring-system-public.git
cd zekat-monitoring-system
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure GitHub Secrets

Add all required secrets as described in [GitHub Secrets Configuration](#github-secrets-configuration).

### 4. Enable GitHub Actions

1. Go to **Actions** tab in your repository
2. Click **I understand my workflows, go ahead and enable them**
3. Verify the "Zakat Monitor" workflow appears in the list

### 5. Test Manual Run

1. Go to **Actions** → **Zakat Monitor**
2. Click **Run workflow** dropdown
3. Select branch (usually `main`)
4. Click **Run workflow** button
5. Wait for completion (usually 1-2 minutes)
6. Check run logs for any errors

---

## Usage

### Automated Execution (Recommended)

The system runs automatically via GitHub Actions:

- **Schedule**: First Monday of every month at 10:00 AM UTC
- **Cron**: `0 10 * * 1` (every Monday at 10AM UTC) — the job checks if the date is the 1st-7th and skips otherwise
- **Workflow File**: `.github/workflows/zakat-monitor.yml`

**No manual intervention required** - just ensure GitHub Secrets are configured.

### Manual Execution

#### Via GitHub Actions (Web UI)

1. Go to **Actions** tab
2. Select **Zakat Monitor** workflow
3. Click **Run workflow** button
4. Choose branch and click **Run workflow**

#### Via Local Command Line

```bash
# Set environment variables
export EMAIL_USERNAME="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export SENDER_EMAIL="sender@gmail.com"
export RECIPIENT_EMAIL="recipient@gmail.com"
export ZAKAT_ENCRYPTION_KEY="your-fernet-key"
export BAM_ACCOUNT="your-bam-account"
export EUR_ACCOUNT="your-eur-account"
export NISAB_FALLBACK_BAM="24624.0"
export ADDITIONAL_ASSETS="0.00"

# Optional: Company source
export COMPANY_EMAIL_USERNAME="company@gmail.com"
export COMPANY_EMAIL_PASSWORD="company-app-password"
export COMPANY_BAM_ACCOUNT="company-bam-account"
export COMPANY_EUR_ACCOUNT="company-eur-account"

# Run the script
python zakat_monitor.py
```

### Viewing Logs

#### GitHub Actions Logs

1. Go to **Actions** tab
2. Click on workflow run
3. Click on "Run Zakat Monitor" job
4. Expand step logs

#### Local Execution Logs

```bash
cat zakat_monitor.log
```

---

## Troubleshooting

### Common Issues

#### 1. No Emails Found

**Symptoms:** "No statements found for BAM/EUR account"

**Solutions:**
- Verify emails are in Gmail inbox (not archived/trash)
- Check sender is `izvodi@procreditbank.ba`
- Ensure statements have PDF attachments
- Verify account numbers in secrets match PDF filenames exactly
- Check spam/promotions folders

#### 2. PDF Parsing Failures

**Symptoms:** "Could not extract balance from PDF"

**Solutions:**
- Verify PDF is not password-protected
- Check PDF is from ProCredit Bank Bosnia (system only supports this format)
- Ensure PDF has 6-column table structure
- Try running with debug logging:
  ```python
  # In zakat_monitor.py, line ~26
  logging.basicConfig(level=logging.DEBUG)  # Changed from INFO
  ```

#### 3. Gmail Authentication Failed

**Symptoms:** "IMAP authentication failed"

**Solutions:**
- Use **App Password**, NOT your regular Gmail password
- Ensure 2-factor authentication is enabled on Gmail
- Check `EMAIL_USERNAME` and `EMAIL_PASSWORD` secrets are correct
- Verify IMAP is enabled in Gmail settings
- Try generating a new App Password

#### 4. Nisab Fetching Failed

**Symptoms:** "Could not extract nisab from zekat.ba"

**Expected Behavior:** This is a known limitation (zekat.ba loads values via JavaScript)

**Solution:**
- System automatically uses `NISAB_FALLBACK_BAM` value
- Update this secret quarterly:
  1. Visit https://zekat.ba manually
  2. Note current nisab value (as of Jan 2026: 24,624.00 BAM)
  3. Update `NISAB_FALLBACK_BAM` GitHub Secret
  4. Recommended frequency: Check every 3 months

#### 5. Currency Conversion Issues

**Symptoms:** Incorrect EUR to BAM conversion

**Solutions:**
- Current fixed rate: **1.955830**
- Bosnia's currency is pegged to EUR (rate is stable)
- If rate changes significantly, update `EUR_TO_BAM_RATE` in `zakat_monitor.py:127`

#### 6. Encryption Errors

**Symptoms:** "Could not load encrypted balance history"

**Solutions:**
- Verify `ZAKAT_ENCRYPTION_KEY` secret is set correctly
- Check key hasn't been modified or corrupted
- If key is lost, delete `zakat_history_encrypted.json` and start fresh:
  ```bash
  git rm zakat_history_encrypted.json
  git commit -m "Reset encrypted history"
  git push
  ```
- Generate new encryption key and update secret

#### 7. GitHub Actions Not Running

**Symptoms:** Workflow doesn't run on schedule

**Solutions:**
- Verify GitHub Actions are enabled (Actions tab)
- Check workflow file exists: `.github/workflows/zakat-monitor.yml`
- Ensure repository isn't archived
- Check GitHub Actions usage limits (private repos have monthly limits)
- Try manual trigger to test if workflow works

### Debug Mode

Enable detailed logging:

```python
# In zakat_monitor.py, around line 26
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zakat_monitor.log'),
        logging.StreamHandler()
    ]
)
```

---

## Maintenance

### Monthly Tasks

- **Review email reports** for accuracy
- **Verify nisab threshold** is current (check zekat.ba)
- **Monitor GitHub Actions** runs for failures

### Quarterly Tasks (Every 3 Months)

- **Update NISAB_FALLBACK_BAM** secret with current value from zekat.ba
- **Review additional assets** (update `ADDITIONAL_ASSETS` if changed)
- **Check for bank PDF format changes** (if parsing suddenly fails)

### Yearly Tasks

- **Rotate App Passwords** (regenerate Gmail App Password)
- **Review total setup** (verify all accounts still monitored)
- **Backup encrypted history** (download `zakat_history_encrypted.json`)
- **Update dependencies** (check for security patches in requirements.txt)

### Security Audits

- Review repository access logs (Settings → Security → Audit log)
- Verify no unauthorized workflow runs
- Ensure encryption key hasn't been exposed
- Check that repository remains private

---

## Advanced Configuration

### Adding Company Source

To monitor a company bank account in addition to personal:

1. Add all 4 company secrets (see [GitHub Secrets Configuration](#github-secrets-configuration))
2. All 4 must be set for company source to activate
3. System will automatically detect and process both sources
4. Email reports will show separate sections for personal and company accounts

### Customizing for Different Banks

Currently supports **ProCredit Bank Bosnia** only. To add other banks:

1. **Obtain sample statements** from your bank
2. **Analyze PDF structure** (table format, column positions)
3. **Update search criteria** in `search_bank_statements()` method
4. **Add regex patterns** to `extract_balance_from_procredit_pdf()` method
5. **Test thoroughly** with actual statements

### Adjusting Schedule

Edit `.github/workflows/zakat-monitor.yml`:

```yaml
on:
  schedule:
    # Current: every Monday at 10AM UTC (job skips if day > 7)
    - cron: '0 10 * * 1'
```

The "first Monday" logic is handled by a step in the job that checks if the current day is between 1-7. To change the time or day, edit the cron expression. To change the "first week" logic, edit the `Check if first Monday of month` step.

---

## Important Disclaimer

**This system is for informational purposes only.**

- **Verify all calculations independently** - manually check balances and dates
- **Consult qualified Islamic scholars** for final zakat determinations, especially for:
  - Complex financial situations
  - Business asset valuations
  - Mixed zakatable/non-zakatable assets
  - Debt considerations
- **Check zekat.ba regularly** for current official nisab values
- **This tool assists with tracking** but does not replace proper Islamic guidance
- **Update quarterly** - nisab values change with gold prices

**The developers are not responsible for any financial or religious decisions made based on this system's output.**

---

## Support

For issues or questions:

1. **Check this guide** - most common issues covered above
2. **Review GitHub Issues** - https://github.com/kasapovicc/zekat-monitoring-system-public/issues
3. **Create new issue** with:
   - Clear description of problem
   - Relevant log excerpts (remove sensitive data!)
   - Python version and OS
   - Steps to reproduce

---

## Building from Source

### macOS App

Requires Python 3.11+ and PyInstaller:

```bash
pip install -r requirements-app.txt
pip install pyinstaller
python3 build.py
open dist/Zekat.app
```

### Running in Development

Start the FastAPI server without the menubar wrapper:

```bash
pip install -r requirements-app.txt
python3 run_app.py
# Opens at http://localhost:8000
```

---

## Technical Details

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions (Monthly)                    │
│           Cron: 0 10 1-7 * 1 (First Monday @ 10AM UTC)          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Multi-Source Email Orchestrator                │
│          Process Personal + Company Sources (Optional)          │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
                ▼                             ▼
    ┌───────────────────────┐     ┌───────────────────────┐
    │ Personal Gmail IMAP   │     │ Company Gmail IMAP    │
    └───────┬───────────────┘     └───────┬───────────────┘
            │                             │
            ▼                             ▼
    ┌───────────────────────┐     ┌───────────────────────┐
    │  PDF Download & Parse │     │  PDF Download & Parse │
    └───────┬───────────────┘     └───────┬───────────────┘
            │                             │
     ┌──────┴─────┐                ┌──────┴─────┐
     ▼            ▼                ▼            ▼
┌────────┐  ┌────────┐        ┌────────┐  ┌────────┐
│ BAM    │  │ EUR    │        │ BAM    │  │ EUR    │
└────┬───┘  └───┬────┘        └────┬───┘  └───┬────┘
     │          │                  │          │
     │    ┌─────┴──────┐          │    ┌─────┴──────┐
     │    │EUR → BAM   │          │    │EUR → BAM   │
     │    │× 1.95583   │          │    │× 1.95583   │
     │    └─────┬──────┘          │    └─────┬──────┘
     └──────────┴────┐            └──────────┴────┐
                     ▼                            ▼
          ┌──────────────────┐        ┌──────────────────┐
          │  Personal Total  │        │  Company Total   │
          └─────────┬────────┘        └─────────┬────────┘
                    └──────────┬────────────────┘
                               ▼
                 ┌──────────────────────────┐
                 │   Grand Total (BAM)      │
                 └─────────┬────────────────┘
                           │
                           ▼
                 ┌──────────────────────────┐
                 │  Nisab Threshold Check   │
                 │  (zekat.ba or fallback)  │
                 └─────────┬────────────────┘
                           │
                           ▼
                 ┌──────────────────────────┐
                 │  12 Hijri Month Check    │
                 └─────────┬────────────────┘
                           │
                           ▼
                 ┌──────────────────────────┐
                 │  Zakat: 2.5% if due      │
                 └─────────┬────────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
     ┌───────────────────┐        ┌──────────────────┐
     │ Encrypted Storage │        │  HTML Email      │
     │ (GitHub Commit)   │        │  Notification    │
     └───────────────────┘        └──────────────────┘
```

### Processing Steps

1. **Email Retrieval**: Connects to Gmail IMAP, searches for ProCredit Bank statements
2. **PDF Parsing**: Extracts balance from 6-column ProCredit table format using regex
3. **Currency Conversion**: EUR balances × 1.95583 → BAM
4. **Nisab Check**: Fetches current threshold from zekat.ba (fallback: 24,624.00 BAM)
5. **Date Conversion**: Statement date (Gregorian) → Hijri calendar
6. **History Update**: Appends to encrypted history, deduplicates, keeps 24 months
7. **Eligibility Check**: Counts consecutive months above nisab
8. **Zakat Calculation**: If 12+ months above nisab → 2.5% of total assets
9. **Storage**: Encrypts history, commits to GitHub
10. **Notification**: Sends HTML email report

### macOS App Architecture

- **Main process**: rumps menubar + FastAPI server + APScheduler
- **Window process**: pywebview launched as subprocess
- **Dev server**: `run_app.py` runs FastAPI standalone without menubar
- **Config**: Argon2id KDF → Fernet encryption at `~/Library/Application Support/Zekat/config.enc`
- **Build**: `build.py` + `zekat.spec` → PyInstaller → `dist/Zekat.app`

### Dependencies

**Script** (`requirements.txt`):
```
PyPDF2, requests, cryptography, hijri-converter, certifi
```

**App** (`requirements-app.txt`):
```
fastapi, uvicorn, pywebview (macOS), rumps (macOS), APScheduler,
argon2-cffi, jinja2, python-multipart, httpx
```

---

## File Structure

```
zekat-monitoring-system/
├── .github/
│   └── workflows/
│       ├── zakat-monitor.yml         # Monthly monitoring workflow
│       └── test.yml                  # Test workflow (push/PR)
├── app/                              # macOS desktop app
│   ├── api/
│   │   ├── routes.py                 # FastAPI API endpoints
│   │   ├── views.py                  # HTML template views
│   │   └── schemas.py                # Pydantic request/response models
│   ├── storage/
│   │   ├── config.py                 # Encrypted config (Argon2id + Fernet)
│   │   └── history.py                # Encrypted history storage
│   ├── templates/                    # Jinja2 HTML templates
│   │   ├── setup.html                # 5-step setup wizard
│   │   ├── dashboard.html            # Balance & zakat status
│   │   ├── settings.html             # Config management
│   │   └── history.html              # Past analysis results
│   ├── main.py                       # Menubar app entry point (rumps)
│   ├── adapter.py                    # Bridge: app config → ZakatMonitor
│   ├── scheduler.py                  # APScheduler monthly runs
│   ├── window.py                     # pywebview subprocess
│   └── paths.py                      # Frozen/dev path resolution
├── docs/
│   └── setup.md                      # This file
├── tests/                            # Pytest test suite
├── zakat_monitor.py                  # Core monitoring script
├── run_app.py                        # Dev server launcher
├── run_native_app.py                 # PyInstaller entry point
├── build.py                          # Build script → dist/Zekat.app
├── zekat.spec                        # PyInstaller spec
├── requirements.txt                  # Script dependencies
├── requirements-app.txt              # App dependencies
├── zakat_history_encrypted.json      # Encrypted balance history (runtime)
├── README.md                         # Project overview
├── LICENSE                           # MIT License
└── .gitignore                        # Git ignore rules
```

---

**Need help?** Open an issue on GitHub with details about your setup and error logs (remove sensitive data first).
