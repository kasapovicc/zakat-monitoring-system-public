#!/usr/bin/env python3
"""
Zakat Nisab Monitoring System - Multi-Account Version with GitHub Integration
Monitors bank statements from both BAM and EUR accounts and calculates zakat eligibility
Automatically persists balance history in GitHub repository for 12-month tracking
"""

import os
import json
import re
import smtplib
import imaplib
import logging
import subprocess
from datetime import datetime
import requests
import PyPDF2
from cryptography.fernet import Fernet
from hijri_converter import Hijri, Gregorian
from typing import Dict, List, Optional, Tuple, TypedDict
from email.utils import parsedate_to_datetime
from email.header import decode_header as decode_mime_header
import io
import ssl

# --- Constants ---
ZAKAT_RATE = 0.025
MAX_PDF_PAGES = 20
MAX_PDF_SIZE_BYTES = 5 * 1024 * 1024
MIN_PDF_SIZE_BYTES = 1000
MAX_HISTORY_MONTHS = 24
HIJRI_YEAR_MONTHS = 12
NISAB_MIN_BAM = 5000
NISAB_MAX_BAM = 35000
MAX_REASONABLE_BALANCE = 100_000_000


# --- Structured return types ---

class BalanceInfo(TypedDict, total=False):
    starting_balance: float
    ending_balance: float
    period_start: str
    period_end: str
    currency: str
    account_holder: str
    pdf_filename: str
    filename_account: Optional[str]


class AccountBalance(TypedDict):
    balance: float
    balance_bam: float
    period: Optional[str]
    found: bool
    account_number: str
    pdf_filename: str
    filename_account_match: bool


class AnalysisResult(TypedDict):
    bank_balance: float
    additional_assets: float
    total_assets: float
    nisab_threshold: float
    above_nisab: bool
    consecutive_months_above_nisab: int
    hijri_year_complete: bool
    zakat_due: bool
    zakat_amount: float


# Configure logging to avoid sensitive data in logs
from pathlib import Path
_log_dir = Path.home() / '.zekat'
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / 'zakat_monitor.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(_log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def parse_bosnian_number(s: str) -> float:
    """Convert Bosnian number format (1.234,56) to float."""
    return float(s.replace('.', '').replace(',', '.'))


def parse_email_date(date_str: str) -> datetime:
    """Parse email date string into a datetime for sorting."""
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        try:
            date_match = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', date_str)
            if date_match:
                day, month_str, year = date_match.groups()
                month_map = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = month_map.get(month_str.lower(), 1)
                return datetime(int(year), month, int(day))
        except (ValueError, KeyError):
            pass
    return datetime(1970, 1, 1)


class ZakatMonitor:
    @staticmethod
    def _mask_account(account_number: str) -> str:
        try:
            if not account_number:
                return "****"
            return f"****{account_number[-4:]}"
        except Exception:
            return "****"

    @staticmethod
    def _mask_email(email_addr: Optional[str]) -> str:
        if not email_addr:
            return "***@***"
        try:
            local, _, domain = email_addr.partition('@')
            local_mask = local[0] + "***" if local else "***"
            domain_mask = domain.split('.')
            if len(domain_mask) >= 2:
                domain_mask[0] = "***"
                domain = '.'.join(domain_mask)
            else:
                domain = "***"
            return f"{local_mask}@{domain}"
        except Exception:
            return "***@***"

    @staticmethod
    def _mask_amount(value: Optional[float]) -> str:
        return "***"

    @staticmethod
    def _validate_email(email: str) -> bool:
        """Validate email address format"""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def _validate_date_format(date_str: str) -> bool:
        """Validate DD.MM.YYYY date format"""
        if not date_str:
            return False
        pattern = r'^\d{2}\.\d{2}\.\d{4}$'
        if not re.match(pattern, date_str):
            return False
        try:
            datetime.strptime(date_str, '%d.%m.%Y')
            return True
        except ValueError:
            return False

    @staticmethod
    def _validate_balance(balance: float) -> bool:
        """Validate balance is a reasonable positive number"""
        return isinstance(balance, (int, float)) and 0 <= balance <= MAX_REASONABLE_BALANCE

    def __init__(self):
        """Initialize the Zakat Monitor with configuration"""
        self.config = self._load_config()
        # Debug: Check which email config variables are set (masked for log)
        email_cfg = self.config.get('email', {})
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"EMAIL_USERNAME set? {'yes' if bool(email_cfg.get('username')) else 'no'}")
            logger.debug(f"EMAIL_PASSWORD set? {'yes' if bool(email_cfg.get('password')) else 'no'}")
        # Encryption key and cipher initialization
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"ZAKAT_ENCRYPTION_KEY set? {'yes' if bool(self.encryption_key) else 'no'}")

        # Build email sources list
        self.email_sources = self._build_email_sources()

        # Keep backward-compatible attributes from primary source
        primary = self.email_sources[0]
        self.BAM_ACCOUNT = primary['bam_account']
        self.EUR_ACCOUNT = primary['eur_account']
        self.EUR_TO_BAM_RATE = 1.955830  # Fixed conversion rate
        
        # Try to get encryption key, fallback if not available
        # The encryption_key and cipher_suite are now initialized in __init__
        
        # Nisab configuration
        self.OFFICIAL_NISAB_URL = "https://zekat.ba"
        self.NISAB_FALLBACK_BAM = float(os.getenv('NISAB_FALLBACK_BAM', '24624.0'))
        
        # Initialize storage for historical data
        self.history_file = 'zakat_history_encrypted.json'
        self.balance_history = self._load_balance_history()

    def _load_config(self) -> Dict:
        """Load configuration from environment variables with validation"""
        config = {
            'email': {
                'imap_server': os.getenv('IMAP_SERVER', 'imap.gmail.com'),
                'imap_port': int(os.getenv('IMAP_PORT', '993')),
                'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                'smtp_port': int(os.getenv('SMTP_PORT', '587')),
                'username': os.getenv('EMAIL_USERNAME'),
                'password': os.getenv('EMAIL_PASSWORD'),
                'sender_email': os.getenv('SENDER_EMAIL'),
                'recipient_email': os.getenv('RECIPIENT_EMAIL')
            },
            'additional_assets': float(os.getenv('ADDITIONAL_ASSETS', '0'))
        }

        # Validate email addresses
        sender = config['email']['sender_email']
        recipient = config['email']['recipient_email']

        if sender and not self._validate_email(sender):
            logger.warning(f"SENDER_EMAIL format appears invalid: {self._mask_email(sender)}")

        if recipient and not self._validate_email(recipient):
            logger.warning(f"RECIPIENT_EMAIL format appears invalid: {self._mask_email(recipient)}")

        return config

    def _build_email_sources(self) -> List[Dict]:
        """Build list of email sources from environment variables

        Primary source is always present; company source is appended only when
        all 4 COMPANY_* vars are set.
        """
        sources = []

        # Primary source (required)
        bam = os.getenv('BAM_ACCOUNT')
        eur = os.getenv('EUR_ACCOUNT')
        if not bam or not eur:
            raise RuntimeError("BAM_ACCOUNT and EUR_ACCOUNT environment variables are required")

        sources.append({
            'name': 'Personal',
            'imap_server': self.config['email']['imap_server'],
            'imap_port': self.config['email']['imap_port'],
            'username': self.config['email']['username'],
            'password': self.config['email']['password'],
            'bam_account': bam,
            'eur_account': eur,
        })

        # Company source (optional -- all 4 vars must be set)
        company_username = os.getenv('COMPANY_EMAIL_USERNAME')
        company_password = os.getenv('COMPANY_EMAIL_PASSWORD')
        company_bam = os.getenv('COMPANY_BAM_ACCOUNT')
        company_eur = os.getenv('COMPANY_EUR_ACCOUNT')

        if all([company_username, company_password, company_bam, company_eur]):
            sources.append({
                'name': 'Company',
                'imap_server': os.getenv('COMPANY_IMAP_SERVER', 'imap.gmail.com'),
                'imap_port': int(os.getenv('COMPANY_IMAP_PORT', '993')),
                'username': company_username,
                'password': company_password,
                'bam_account': company_bam,
                'eur_account': company_eur,
            })
            logger.info(f"Company email source configured: {self._mask_email(company_username)}")

        return sources

    def _get_encryption_key(self) -> bytes:
        """Get encryption key from environment"""
        key_env = os.getenv('ZAKAT_ENCRYPTION_KEY')
        if key_env:
            return key_env.encode()
        raise RuntimeError("ZAKAT_ENCRYPTION_KEY is required but not set. Aborting to avoid plaintext history.")

    def _load_balance_history(self) -> List[Dict]:
        """Load balance history from encrypted file only"""
        try:
            # Encrypted file only
            if os.path.exists(self.history_file) and self.cipher_suite:
                with open(self.history_file, 'rb') as f:
                    encrypted_data = f.read()
                decrypted_data = self.cipher_suite.decrypt(encrypted_data)
                history = json.loads(decrypted_data.decode())
                logger.info(f"Loaded {len(history)} entries from encrypted balance history")
                return history
        except FileNotFoundError:
            logger.info("History file not found, starting fresh")
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted history file (invalid JSON): {e}")
        except Exception as e:
            logger.warning(f"Could not load encrypted balance history: {type(e).__name__}: {e}")

        logger.info("Starting with empty balance history")
        return []

    def _save_balance_history(self):
        """Save balance history (encrypted only) with GitHub Actions support"""
        try:
            if not self.cipher_suite:
                raise RuntimeError("Encryption not initialized; refusing to write plaintext history")
            data = json.dumps(self.balance_history, indent=2).encode()
            encrypted_data = self.cipher_suite.encrypt(data)
            with open(self.history_file, 'wb') as f:
                f.write(encrypted_data)
            logger.info(f"Saved encrypted balance history to {self.history_file}")
            
            # GitHub Actions: Commit history file back to repository for persistence
            if os.getenv('GITHUB_ACTIONS'):
                self._commit_history_to_github()
                
        except Exception as e:
            logger.error(f"Failed to save balance history: {e}")

    def _commit_history_to_github(self):
        """Commit history file back to GitHub repository for persistence"""
        try:
            logger.info("Committing balance history to GitHub repository...")

            # Configure git user locally (required for commits in GitHub Actions)
            subprocess.run(['git', 'config', '--local', 'user.name', 'Zakat Monitor Bot'], check=True)
            subprocess.run(['git', 'config', '--local', 'user.email', 'zakat-monitor@github-actions.local'], check=True)
            
            # Add the history file to git
            history_files = ['zakat_history_encrypted.json', 'zakat_history.json']
            for file in history_files:
                if os.path.exists(file):
                    subprocess.run(['git', 'add', file], check=True)
                    logger.info(f"Added {file} to git staging")
            
            # Check if there are changes to commit
            result = subprocess.run(['git', 'diff', '--cached', '--exit-code'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:  # There are changes to commit
                commit_message = f"Update zakat balance history - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                subprocess.run(['git', 'commit', '-m', commit_message], check=True)
                
                # Push to repository
                subprocess.run(['git', 'push'], check=True)
                logger.info("✅ Successfully committed and pushed balance history to GitHub")
            else:
                logger.info("No changes in balance history to commit")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            logger.error("This might be a permissions issue - check GitHub Actions workflow permissions")
        except Exception as e:
            logger.error(f"Failed to commit history to GitHub: {e}")

    def record_zakat_payment(self, payment_date: Optional[str] = None):
        """Record a zakat payment in the balance history

        Args:
            payment_date: Optional payment date in DD.MM.YYYY format. Defaults to today.
        """
        from datetime import datetime

        # Parse payment date or use today
        if payment_date:
            try:
                # Validate format DD.MM.YYYY
                dt = datetime.strptime(payment_date, '%d.%m.%Y')
                gregorian_date = payment_date
                timestamp = dt.isoformat()
            except ValueError:
                logger.error(f"Invalid date format: {payment_date}. Expected DD.MM.YYYY")
                print(f"❌ Error: Invalid date format '{payment_date}'. Use DD.MM.YYYY format.")
                return
        else:
            now = datetime.now()
            gregorian_date = now.strftime('%d.%m.%Y')
            timestamp = now.isoformat()

        # Create payment marker entry
        payment_entry = {
            'type': 'zakat_paid',
            'timestamp': timestamp,
            'gregorian_date': gregorian_date
        }

        # Load current history
        self.balance_history = self._load_balance_history()

        # Append payment marker
        self.balance_history.append(payment_entry)

        # Save updated history
        self._save_balance_history()

        logger.info(f"✅ Recorded zakat payment for {gregorian_date}")
        print(f"✅ Zakat payment marked as paid on {gregorian_date}")
        print(f"The 12-month counter has been reset. New cycle starts from this date.")

    def connect_to_gmail(self, source: Optional[Dict] = None) -> imaplib.IMAP4_SSL:
        """Connect to Gmail via IMAP

        Args:
            source: Optional email source dict with credentials. If not provided,
                   uses self.config['email'] for backward compatibility.
        """
        try:
            # Use source credentials if provided, otherwise fall back to config
            if source:
                imap_server = source['imap_server']
                imap_port = source['imap_port']
                username = source['username']
                password = source['password']
            else:
                imap_server = self.config['email']['imap_server']
                imap_port = self.config['email']['imap_port']
                username = self.config['email']['username']
                password = self.config['email']['password']

            context = ssl.create_default_context()
            # In PyInstaller bundles, the default CA store may be empty.
            # Fall back to certifi's CA bundle when available.
            try:
                import certifi
                context.load_verify_locations(certifi.where())
            except (ImportError, OSError):
                pass
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, ssl_context=context)
            mail.login(username, password)
            logger.info("Successfully connected to Gmail IMAP server")
            return mail
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication failed: {e}")
            raise
        except ssl.SSLError as e:
            logger.error(f"SSL connection error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Gmail: {type(e).__name__}: {e}")
            raise

    def search_bank_statements_by_account(self, mail: imaplib.IMAP4_SSL, bam_account=None, eur_account=None) -> Dict[str, List[Tuple[str, str]]]:
        """Search for bank statement emails organized by account number

        Args:
            mail: IMAP connection
            bam_account: BAM account number (defaults to self.BAM_ACCOUNT)
            eur_account: EUR account number (defaults to self.EUR_ACCOUNT)
        """
        bam = bam_account or self.BAM_ACCOUNT
        eur = eur_account or self.EUR_ACCOUNT

        try:
            mail.select('inbox')

            # Search specifically for ProCredit Bank emails
            search_criteria = [
                'FROM "izvodi@procreditbank.ba"',
                'FROM "procreditbank.ba" SUBJECT "izvod"',
                'FROM "procreditbank.ba" SUBJECT "IZVOD"'
            ]

            all_statements = []
            for criteria in search_criteria:
                try:
                    status, messages = mail.search(None, criteria)
                    if status == 'OK' and messages[0]:
                        for msg_id in messages[0].split():
                            all_statements.append(msg_id.decode())
                except Exception as e:
                    logger.debug(f"Search criteria '{criteria}' failed: {e}")
                    continue

            # Remove duplicates while preserving order
            unique_statements = list(dict.fromkeys(all_statements))

            # Organize statements by account number
            statements_by_account = {
                bam: [],  # BAM account statements
                eur: []   # EUR account statements
            }
            
            logger.info(f"Found {len(unique_statements)} total emails, organizing by account...")
            
            for stmt_id in unique_statements:
                try:
                    # Fetch email header AND internal date for proper sorting
                    status, msg_data = mail.fetch(stmt_id, '(BODY[HEADER.FIELDS (SUBJECT DATE)] INTERNALDATE)')
                    if status == 'OK' and msg_data:
                        header_raw = msg_data[0][1].decode('utf-8', errors='ignore')

                        # Decode MIME-encoded headers (RFC 2047) so account numbers
                        # are visible even when subject contains non-ASCII chars
                        decoded_parts = decode_mime_header(
                            re.search(r'Subject:\s*(.+)', header_raw, re.IGNORECASE).group(1)
                            if re.search(r'Subject:\s*(.+)', header_raw, re.IGNORECASE)
                            else header_raw
                        )
                        decoded_subject = ""
                        for part_bytes, charset in decoded_parts:
                            if isinstance(part_bytes, bytes):
                                decoded_subject += part_bytes.decode(charset or 'utf-8', errors='ignore')
                            else:
                                decoded_subject += part_bytes
                        # Use decoded subject for account matching, raw header for date
                        header = decoded_subject if decoded_subject else header_raw

                        # Get internal date (when email was received by server)
                        # This is more reliable than parsing the Date header
                        internal_date_info = msg_data[1] if len(msg_data) > 1 else b''
                        internal_date_str = internal_date_info.decode('utf-8', errors='ignore') if internal_date_info else ""

                        # Extract date for sorting - try multiple approaches
                        email_date = ""

                        # Method 1: Use INTERNALDATE if available (most reliable)
                        internal_date_match = re.search(r'INTERNALDATE "([^"]+)"', internal_date_str)
                        if internal_date_match:
                            email_date = internal_date_match.group(1)
                            logger.debug(f"Using internal date: {email_date}")
                        else:
                            # Method 2: Parse Date header as fallback
                            date_match = re.search(r'Date:\s*(.+)', header_raw)
                            email_date = date_match.group(1).strip() if date_match else ""

                        # Determine account based on account number in subject
                        if bam in header:
                            statements_by_account[bam].append((stmt_id, email_date))
                            logger.debug(f"Found BAM statement: {email_date}")
                        elif eur in header:
                            statements_by_account[eur].append((stmt_id, email_date))
                            logger.debug(f"Found EUR statement: {email_date}")
                        else:
                            logger.debug(f"Email {stmt_id} doesn't match known account numbers in subject: {header[:80]}")
                        
                except Exception as e:
                    logger.debug(f"Failed to fetch header for email {stmt_id}: {e}")
                    continue
            
            for account in statements_by_account:
                statements_by_account[account].sort(
                    key=lambda x: parse_email_date(x[1]), 
                    reverse=True  # Most recent first
                )
                
                # Log the sorted order for debugging
                logger.info(f"{self._mask_account(account)} statements sorted by date:")
                for i, (stmt_id, date_str) in enumerate(statements_by_account[account][:3]):  # Show top 3
                    logger.info(f"  {i+1}. {date_str}")
            
            logger.info(f"BAM account ({self._mask_account(bam)}): {len(statements_by_account[bam])} statements")
            logger.info(f"EUR account ({self._mask_account(eur)}): {len(statements_by_account[eur])} statements")

            return statements_by_account

        except Exception as e:
            logger.error(f"Failed to search for bank statements: {e}")
            return {bam: [], eur: []}

    def download_pdf_attachment(self, mail: imaplib.IMAP4_SSL, msg_id: str) -> Optional[Tuple[bytes, str]]:
        """Download PDF attachment from email and return PDF data with filename"""
        try:
            import email as email_module
            
            logger.debug(f"Attempting to download PDF from email ID: {msg_id}")
            
            status, msg_data = mail.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                logger.error(f"Failed to fetch email message: {status}")
                return None
                
            if not msg_data or not msg_data[0] or len(msg_data[0]) < 2:
                logger.error("Email message data is empty or invalid")
                return None
                
            email_body = msg_data[0][1]
            email_message = email_module.message_from_bytes(email_body)
            
            # Check if email is multipart
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = part.get_content_disposition()
                    filename = part.get_filename()
                    
                    # Check for PDF by multiple criteria
                    is_pdf = False
                    
                    # Check filename ends with .pdf and exclude newsletters
                    if filename and filename.lower().endswith('.pdf'):
                        if not filename.lower().startswith('pcb') and 'newsletter' not in filename.lower():
                            is_pdf = True
                    
                    # Check content type
                    elif content_type == 'application/pdf':
                        is_pdf = True
                    
                    # Check octet-stream with PDF filename
                    elif content_type == 'application/octet-stream' and filename and filename.lower().endswith('.pdf'):
                        if not filename.lower().startswith('pcb') and 'newsletter' not in filename.lower():
                            is_pdf = True
                    
                    if is_pdf:
                        pdf_content = part.get_payload(decode=True)
                        # Basic protections: size cap 5MB and minimum size, and reject protected PDFs
                        if pdf_content and MIN_PDF_SIZE_BYTES < len(pdf_content) <= MAX_PDF_SIZE_BYTES:
                            try:
                                reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
                                if getattr(reader, 'is_encrypted', False):
                                    logger.warning("Skipping password-protected PDF")
                                    continue
                                if len(reader.pages) > MAX_PDF_PAGES:
                                    logger.warning("Skipping PDF with excessive pages (>20)")
                                    continue
                            except Exception:
                                # If we cannot parse at this point, still return to allow main parser to handle
                                pass
                            logger.debug("Successfully downloaded PDF for parsing")
                            return (pdf_content, filename or "statement.pdf")
            else:
                # Handle non-multipart emails
                content_type = email_message.get_content_type()
                if content_type == 'application/pdf':
                    pdf_content = email_message.get_payload(decode=True)
                    if pdf_content and MIN_PDF_SIZE_BYTES < len(pdf_content) <= MAX_PDF_SIZE_BYTES:
                        logger.debug("Downloaded PDF from non-multipart email")
                        return (pdf_content, "statement.pdf")
            
            return None

        except email_module.errors.MessageError as e:
            logger.error(f"Email parsing error: {e}")
        except Exception as e:
            logger.error(f"Failed to download PDF attachment: {type(e).__name__}: {e}")
        return None

    def identify_account_from_filename(self, filename: str, bam_account=None, eur_account=None) -> Optional[str]:
        """
        Identify account type from ProCredit Bank PDF filename
        Expected format: account-number_YYYY-MM-DD.pdf

        Args:
            filename: PDF filename to parse
            bam_account: BAM account number (defaults to self.BAM_ACCOUNT)
            eur_account: EUR account number (defaults to self.EUR_ACCOUNT)
        """
        bam = bam_account or self.BAM_ACCOUNT
        eur = eur_account or self.EUR_ACCOUNT

        try:
            if not filename:
                return None

            # Remove .pdf extension
            base_name = filename.replace('.pdf', '').replace('.PDF', '')

            # Split by underscore to get account number
            parts = base_name.split('_')

            if len(parts) >= 1:
                account_number = parts[0]

                if account_number == bam:
                    return 'BAM'
                elif account_number == eur:
                    return 'EUR'

            return None

        except Exception as e:
            logger.debug(f"Could not identify account from filename {filename}: {e}")
            return None

    def extract_balance_from_procredit_pdf(self, pdf_data: bytes) -> Optional[BalanceInfo]:
        """Extract balance information from ProCredit Bank PDF"""
        try:
            pdf_file = io.BytesIO(pdf_data)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            
            balance_info = {}
            
            # Primary focus: Extract "Krajnje stanje" (ending balance) from 6-column table
            # ProCredit table structure:
            # Col1: Početno stanje | Col2: Iznos trans.(Isplate) | Col3: Iznos trans.(Uplate) | Col4: Krajnje stanje | Col5: Broj trans.(Isplate) | Col6: Broj trans.(Uplate)
            # We need Column 4 as the ending balance, not Column 2!

            krajnje_patterns = [
                # Pattern 1: Full 6-column table structure
                # Matches: Starting Balance | Withdrawals | Deposits | Ending Balance | Num Withdrawals | Num Deposits
                # Regex explanation: (\d{1,3}(?:\.\d{3})*,\d{2}) matches numbers like 1.234,56 or 12.345,67
                # \s+ matches whitespace between columns, (\d+) matches integer transaction counts
                r'(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d+)\s+(\d+)',

                # Pattern 2: Header-based extraction (partial table)
                # Matches text between "Početno stanje" and "Krajnje stanje" headers followed by 4 numeric columns
                # .*? matches any characters non-greedily between headers
                r'Početno stanje.*?Krajnje stanje.*?(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})',

                # Pattern 3: Fallback - simple pattern
                # Matches "krajnje stanje" (case insensitive) followed by any non-digit characters then a number
                # [^\d]* matches any non-digit characters (spaces, colons, etc.)
                r'krajnje stanje[^\d]*(\d{1,3}(?:\.\d{3})*,\d{2})',
            ]
            
            for i, pattern in enumerate(krajnje_patterns):
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    try:
                        if i == 0:  # Pattern 1: Full 6-column table
                            balance_info['starting_balance'] = parse_bosnian_number(match.group(1))
                            balance_info['ending_balance'] = parse_bosnian_number(match.group(4))

                            logger.info("6-column table: Starting=***, Ending=***")
                            break

                        elif i == 1:  # Pattern 2: Header-based (4 columns)
                            balance_info['starting_balance'] = parse_bosnian_number(match.group(1))
                            balance_info['ending_balance'] = parse_bosnian_number(match.group(4))

                            logger.info("Header-based: Starting=***, Ending=***")
                            break

                        else:  # Pattern 3: Fallback
                            balance_info['ending_balance'] = parse_bosnian_number(match.group(1))
                            logger.info("Fallback: Ending balance=***")
                            break
                            
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Pattern {i+1} matched but failed to parse: {e}")
                        continue
            
            # Extract starting balance separately if not found
            if 'starting_balance' not in balance_info:
                pocetno_match = re.search(r'Početno stanje[^\d]*(\d{1,3}(?:\.\d{3})*,\d{2})', text, re.IGNORECASE)
                if pocetno_match:
                    balance_info['starting_balance'] = parse_bosnian_number(pocetno_match.group(1))
                    logger.info("Found starting balance separately: ***")
            
            # Extract account holder - use environment variable for privacy
            account_holder = os.getenv('ACCOUNT_HOLDER_NAME')
            if account_holder and account_holder in text:
                balance_info['account_holder'] = account_holder
            
            # Extract dates - handle ProCredit format where date appears BEFORE "Datum do:"
            datum_od_match = re.search(r'Datum od[:\s]*(\d{2}\.\d{2}\.\d{4})', text, re.IGNORECASE)
            datum_do_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s*Datum do', text, re.IGNORECASE)
            
            # Alternative date patterns
            if not datum_do_match:
                datum_do_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s*\n?\s*Datum do', text, re.IGNORECASE)
            if not datum_do_match:
                datum_do_match = re.search(r'Datum do[:\s]*(\d{2}\.\d{2}\.\d{4})', text, re.IGNORECASE)
            
            if datum_od_match:
                balance_info['period_start'] = datum_od_match.group(1)
            
            if datum_do_match:
                balance_info['period_end'] = datum_do_match.group(1)
            
            # Fallback date extraction
            if not datum_od_match or not datum_do_match:
                all_dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', text)
                if len(all_dates) >= 2:
                    if not datum_od_match:
                        balance_info['period_start'] = all_dates[0]
                    if not datum_do_match:
                        balance_info['period_end'] = all_dates[-1]
                elif len(all_dates) == 1:
                    balance_info['period_start'] = all_dates[0]
                    balance_info['period_end'] = all_dates[0]
                else:
                    current_date = datetime.now().strftime('%d.%m.%Y')
                    balance_info['period_start'] = current_date
                    balance_info['period_end'] = current_date
            
            # Currency is determined by account processing
            balance_info['currency'] = 'Unknown'
            
            # Validate that we found essential information
            if 'ending_balance' not in balance_info:
                logger.error("Could not extract ending balance from PDF")
                return None

            # Validate extracted balance is reasonable
            if not self._validate_balance(balance_info['ending_balance']):
                logger.error(f"Extracted balance appears invalid: {balance_info['ending_balance']}")
                return None
            
            logger.info(f"Successfully extracted: Starting=***, Ending=***, "
                       f"Period: {balance_info.get('period_start')} to {balance_info.get('period_end')}")
            
            return balance_info

        except PyPDF2.errors.PdfReadError as e:
            logger.error(f"PDF read error (file may be corrupted): {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract balance from PDF: {type(e).__name__}: {e}")
            return None

    def process_multi_account_statements(self, mail: imaplib.IMAP4_SSL, bam_account=None, eur_account=None) -> Optional[Dict]:
        """Process statements from both BAM and EUR accounts and combine balances

        Args:
            mail: IMAP connection
            bam_account: BAM account number (defaults to self.BAM_ACCOUNT)
            eur_account: EUR account number (defaults to self.EUR_ACCOUNT)
        """
        bam = bam_account or self.BAM_ACCOUNT
        eur = eur_account or self.EUR_ACCOUNT

        try:
            # Search for statements organized by account
            statements_by_account = self.search_bank_statements_by_account(mail, bam_account=bam, eur_account=eur)

            account_balances = {}
            latest_period = None

            # Process each account type
            for account_number, currency in [(bam, 'BAM'), (eur, 'EUR')]:
                statements = statements_by_account.get(account_number, [])
                
                if not statements:
                    logger.warning(f"No statements found for {currency} account ({account_number})")
                    account_balances[currency] = {
                        'balance': 0.0,
                        'balance_bam': 0.0,
                        'period': None,
                        'found': False,
                        'account_number': account_number,
                        'pdf_filename': 'none',
                        'filename_account_match': False
                    }
                    continue
                
                logger.info(f"Processing {currency} account: {len(statements)} statements available")
                
                # Try to get PDF from the most recent statement first
                balance_info = None
                for i, (stmt_id, email_date) in enumerate(statements[:3]):  # Try up to 3 most recent
                    logger.info(f"Trying {currency} statement {i+1} (Date: {email_date})")
                    pdf_result = self.download_pdf_attachment(mail, stmt_id)
                    
                    if pdf_result:
                        pdf_data, filename = pdf_result
                        # Avoid logging full filename (may contain identifiers)
                        logger.info("Downloaded PDF for processing")
                        
                        # Double-check account identification using filename
                        filename_account = self.identify_account_from_filename(filename, bam_account=bam, eur_account=eur)
                        if filename_account and filename_account != currency:
                            logger.warning(f"Account mismatch: Email suggested {currency} but filename suggests {filename_account}")
                            logger.info(f"Using filename-based identification: {filename_account}")
                        
                        balance_info = self.extract_balance_from_procredit_pdf(pdf_data)
                        if balance_info and 'ending_balance' in balance_info:
                            # Add filename information to balance_info
                            # Store sanitized filename (mask any leading account digits)
                            balance_info['pdf_filename'] = 'statement.pdf'
                            balance_info['filename_account'] = filename_account
                            logger.info(f"Successfully extracted {currency} balance: *** {balance_info.get('currency', currency)}")
                            break
                        else:
                            logger.warning(f"Could not extract balance from {currency} statement {i+1} ({filename})")
                    else:
                        logger.warning(f"Could not download PDF from {currency} statement {i+1}")
                
                if balance_info and 'ending_balance' in balance_info:
                    original_balance = balance_info['ending_balance']
                    
                    # Set currency based on account type
                    balance_info['currency'] = currency
                    
                    # Convert EUR to BAM if needed
                    if currency == 'EUR':
                        balance_bam = original_balance * self.EUR_TO_BAM_RATE
                        logger.info("Converted EUR to BAM: *** EUR × 1.95583 = *** BAM")
                    else:
                        balance_bam = original_balance
                    
                    account_balances[currency] = {
                        'balance': original_balance,
                        'balance_bam': balance_bam,
                        'period': balance_info.get('period_end'),
                        'found': True,
                        'account_number': account_number,
                        'pdf_filename': balance_info.get('pdf_filename', 'unknown'),
                        'filename_account_match': balance_info.get('filename_account') == currency
                    }
                    
                    # Track the latest period for dating purposes
                    if balance_info.get('period_end'):
                        current_period = balance_info['period_end']
                        if not latest_period:
                            latest_period = current_period
                        else:
                            # Convert DD.MM.YYYY format to datetime for proper comparison
                            try:
                                current_dt = datetime.strptime(current_period, '%d.%m.%Y')
                                latest_dt = datetime.strptime(latest_period, '%d.%m.%Y')
                                if current_dt > latest_dt:
                                    latest_period = current_period
                                    logger.debug(f"Updated latest period to {current_period}")
                            except ValueError as e:
                                logger.warning(f"Could not parse date for comparison: {e}")
                                # Fallback to string comparison
                                if current_period > latest_period:
                                    latest_period = current_period
                
                else:
                    logger.error(f"Failed to extract balance from {currency} account")
                    account_balances[currency] = {
                        'balance': 0.0,
                        'balance_bam': 0.0,
                        'period': None,
                        'found': False,
                        'account_number': account_number,
                        'pdf_filename': 'none',
                        'filename_account_match': False
                    }
            
            # Calculate total BAM balance
            total_bam_balance = account_balances['BAM']['balance_bam'] + account_balances['EUR']['balance_bam']
            
            # Create combined balance info
            combined_info = {
                'bam_account': account_balances['BAM'],
                'eur_account': account_balances['EUR'],
                'total_balance_bam': total_bam_balance,
                'period_end': latest_period or datetime.now().strftime('%d.%m.%Y'),
                'conversion_rate': self.EUR_TO_BAM_RATE,
                'currency': 'BAM',  # Total is always in BAM
                'ending_balance': total_bam_balance  # For compatibility with existing code
            }
            
            logger.info(f"=== MULTI-ACCOUNT SUMMARY ===")
            logger.info(f"BAM Account: *** BAM (found: {account_balances['BAM']['found']})")
            logger.info(f"EUR Account: *** EUR = *** BAM (found: {account_balances['EUR']['found']})")
            logger.info("Total: *** BAM")
            logger.info(f"Latest period: {latest_period}")
            
            return combined_info
            
        except Exception as e:
            logger.error(f"Failed to process multi-account statements: {e}")
            return None

    def _process_all_sources(self) -> Optional[Dict]:
        """Process all email sources and merge results into a grand total

        Loops over self.email_sources, connects to each Gmail account, processes
        statements, and combines results with per-source breakdowns.

        Sets self._source_diagnostics with per-source failure details for error reporting.
        """
        all_source_results = []
        self._source_diagnostics = []

        for source in self.email_sources:
            source_name = source['name']
            logger.info(f"=== Processing {source_name} email source ===")
            try:
                mail = self.connect_to_gmail(source)
                result = self.process_multi_account_statements(
                    mail, bam_account=source['bam_account'], eur_account=source['eur_account']
                )
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass

                if result:
                    result['source_name'] = source_name
                    all_source_results.append(result)
                    self._source_diagnostics.append(f"{source_name}: OK")
                else:
                    self._source_diagnostics.append(f"{source_name}: no balance data returned")
            except Exception as e:
                logger.error(f"Failed to process {source_name} source: {e}")
                self._source_diagnostics.append(f"{source_name}: {type(e).__name__}: {e}")
                continue

        if not all_source_results:
            return None

        grand_total_bam = sum(r.get('total_balance_bam', 0) for r in all_source_results)
        latest_period = max(
            (r.get('period_end', '') for r in all_source_results),
            default=datetime.now().strftime('%d.%m.%Y')
        )

        return {
            'sources': all_source_results,
            'total_balance_bam': grand_total_bam,
            'ending_balance': grand_total_bam,
            'period_end': latest_period or datetime.now().strftime('%d.%m.%Y'),
            'conversion_rate': self.EUR_TO_BAM_RATE,
            'currency': 'BAM',
            # Backward compat: keep primary source keys
            'bam_account': all_source_results[0].get('bam_account', {}),
            'eur_account': all_source_results[0].get('eur_account', {}),
        }

    def get_official_nisab_bam(self) -> Optional[float]:
        """Fetch current official nisab value from zekat.ba"""
        nisab_urls = [
            'https://zekat.ba',
            'https://zekat.ba/nisab',
            'https://zekat.ba/kalkulator'
        ]
        
        nisab_patterns = [
            r'Aktuelni nisab:\s*(\d{1,2}\.\d{3},\d{2})\s*KM',
            r'Nisab:\s*(\d{1,2}\.\d{3},\d{2})\s*KM',
            r'nisab.*?(\d{1,2}\.\d{3},\d{2}).*?KM'
        ]
        
        for url in nisab_urls:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                logger.info(f"Nisab request to {url} - Status: {response.status_code}")
                
                if response.status_code == 200:
                    content = response.text.lower()
                    
                    for i, pattern in enumerate(nisab_patterns):
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            try:
                                nisab_str = match.group(1)
                                nisab_value = parse_bosnian_number(nisab_str)

                                if NISAB_MIN_BAM <= nisab_value <= NISAB_MAX_BAM:
                                    logger.info(f"Found nisab: {nisab_value} BAM from {url} using pattern {i+1}")
                                    return nisab_value
                                else:
                                    logger.warning(f"Nisab value {nisab_value} seems out of range")
                                    
                            except (ValueError, IndexError) as e:
                                logger.debug(f"Pattern {i+1} matched but failed to parse: {e}")
                                continue
                        else:
                            logger.debug(f"Pattern {i+1} did not match")
                else:
                    logger.warning(f"HTTP {response.status_code} from {url}")
                    
            except Exception as e:
                logger.error(f"Failed to fetch from {url}: {str(e)}")
                continue
        
        logger.warning("Could not extract nisab from zekat.ba")
        return None

    def calculate_nisab_threshold(self) -> Tuple[float, str]:
        """Calculate nisab threshold"""
        
        # Try official website first
        official_nisab = self.get_official_nisab_bam()
        if official_nisab:
            source = f"Official zekat.ba website (fetched {datetime.now().strftime('%Y-%m-%d %H:%M')})"
            return official_nisab, source
        
        # Fallback to configured value
        nisab_bam = self.NISAB_FALLBACK_BAM
        source = f"Fallback configuration ({nisab_bam} BAM)"
        
        return nisab_bam, source

    def convert_gregorian_to_hijri(self, date_str: str) -> Dict:
        """Convert Gregorian date to Hijri"""
        try:
            day, month, year = map(int, date_str.split('.'))
            gregorian_date = Gregorian(year, month, day)
            hijri_date = gregorian_date.to_hijri()
            
            return {
                'hijri_year': hijri_date.year,
                'hijri_month': hijri_date.month,
                'hijri_day': hijri_date.day,
                'gregorian_date': date_str
            }
        except Exception as e:
            logger.error(f"Failed to convert date {date_str}: {e}")
            return {'gregorian_date': date_str}

    def check_hijri_year_threshold(self, total_assets: float, nisab_threshold: float,
                                 current_date: Dict, bank_balance: float) -> AnalysisResult:
        """Check if balance has been above nisab for 12 consecutive Hijri months"""
        
        current_entry = {
            'balance': total_assets,
            'nisab_threshold': nisab_threshold,
            'above_nisab': total_assets >= nisab_threshold,
            'hijri_year': current_date.get('hijri_year'),
            'hijri_month': current_date.get('hijri_month'),
            'gregorian_date': current_date.get('gregorian_date'),
            'timestamp': datetime.now().isoformat()
        }
        
        # Deduplicate: Remove any old entries for the same Gregorian date before appending new one
        # Use Gregorian date for deduplication as it's more stable than Hijri conversion
        current_gregorian_date = current_entry.get('gregorian_date', '')
        
        self.balance_history = [
            entry for entry in self.balance_history
            if entry.get('gregorian_date', '') != current_gregorian_date
        ]
        self.balance_history.append(current_entry)
        self.balance_history = self.balance_history[-MAX_HISTORY_MONTHS:]
        
        # Count consecutive months above nisab
        consecutive_months = 0
        sorted_history = sorted(self.balance_history, key=lambda x: x['timestamp'])

        for entry in reversed(sorted_history):
            # Payment marker resets the cycle
            if entry.get('type') == 'zakat_paid':
                break
            if entry['above_nisab']:
                consecutive_months += 1
            else:
                break

        # Apply year progress override if set (for migrating existing tracking).
        # The override represents N months of prior history before the app started.
        # Real history builds on top: first entry = the month the override was set,
        # each subsequent month adds 1.  If the streak breaks (balance below nisab),
        # the override no longer applies.
        override = getattr(self, 'year_progress_override', None)
        if override and consecutive_months > 0:
            override_months = override.get('months_above_nisab', 0)
            # First history entry is concurrent with the override; don't double-count
            effective = override_months + max(0, consecutive_months - 1)
            if effective > consecutive_months:
                logger.info(f"Applying year progress override: {consecutive_months} -> {effective} months "
                           f"(override={override_months} + {consecutive_months - 1} new)")
                consecutive_months = effective

        hijri_year_complete = consecutive_months >= HIJRI_YEAR_MONTHS
        zakat_amount = total_assets * ZAKAT_RATE if hijri_year_complete else 0
        
        return {
            'bank_balance': bank_balance,
            'additional_assets': self.config['additional_assets'],
            'total_assets': total_assets,
            'nisab_threshold': nisab_threshold,
            'above_nisab': total_assets >= nisab_threshold,
            'consecutive_months_above_nisab': consecutive_months,
            'hijri_year_complete': hijri_year_complete,
            'zakat_due': hijri_year_complete,
            'zakat_amount': zakat_amount
        }

    def generate_encrypted_report(self, analysis_result: Dict, nisab_source: str, 
                                multi_account_info: Dict) -> str:
        """Generate comprehensive report with zakat analysis including multi-account details (NO BALANCE HISTORY)"""
        
        if "Fallback configuration" in nisab_source:
            nisab_source = "Manual GitHub secret configuration (fallback)"
        
        # Extract account details for detailed reporting
        bam_info = multi_account_info.get('bam_account', {})
        eur_info = multi_account_info.get('eur_account', {})
        
        # NOTE: Balance history table is REMOVED as requested
        
        # Create styled HTML email
        report = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: #2c5f4a; color: white; padding: 20px; text-align: center; }}
        .section {{ margin: 20px 0; padding: 15px; border-left: 4px solid #2c5f4a; background-color: #f9f9f9; }}
        .section-title {{ font-size: 18px; font-weight: bold; color: #2c5f4a; margin-bottom: 10px; }}
        .balance-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
        .balance-label {{ font-weight: bold; }}
        .balance-value {{ color: #2c5f4a; font-weight: bold; }}
        .status-yes {{ color: #27ae60; font-weight: bold; }}
        .status-no {{ color: #e74c3c; font-weight: bold; }}
        .calculation {{ background-color: #fff; padding: 15px; border: 2px solid #2c5f4a; margin: 10px 0; }}
        .footer {{ font-size: 12px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
        .progress-bar {{ width: 100%; background-color: #f0f0f0; border-radius: 10px; margin: 10px 0; }}
        .progress-fill {{ height: 20px; background-color: #2c5f4a; border-radius: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🕌 ZAKAT NISAB ANALYSIS REPORT</h1>
        <p>Generated: {datetime.now().strftime('%d.%m.%Y at %H:%M:%S')}</p>
    </div>

"""

        # Generate account sections based on available sources
        sources = multi_account_info.get('sources', [])

        if sources:
            # Multi-source mode: render each source separately
            for source in sources:
                source_name = source.get('source_name', 'Unknown')
                source_bam = source.get('bam_account', {})
                source_eur = source.get('eur_account', {})
                source_total = source.get('total_balance_bam', 0)

                report += f"""
    <div class="section">
        <div class="section-title">📊 {source_name.upper()} ACCOUNTS</div>
        <div class="balance-row">
            <span class="balance-label">BAM Account:</span>
            <span class="balance-value">{source_bam.get('balance', 0):.2f} BAM</span>
        </div>
        <div style="margin-left: 20px; color: #666; font-size: 14px;">
            Source File: {source_bam.get('pdf_filename', 'none')}
            • Status: {'✅ Found' if source_bam.get('found') else '❌ Not Found'}
        </div>

        <div class="balance-row" style="margin-top: 15px;">
            <span class="balance-label">EUR Account:</span>
            <span class="balance-value">{source_eur.get('balance', 0):.2f} EUR</span>
        </div>
        <div style="margin-left: 20px; color: #666; font-size: 14px;">
            Source File: {source_eur.get('pdf_filename', 'none')}
            • Status: {'✅ Found' if source_eur.get('found') else '❌ Not Found'}
        </div>

        <div style="margin-top: 15px; padding: 10px; background-color: #e8f5e8; border-radius: 5px;">
            <strong>EUR to BAM Conversion:</strong><br>
            {source_eur.get('balance', 0):.2f} EUR × {multi_account_info.get('conversion_rate', self.EUR_TO_BAM_RATE)} = {source_eur.get('balance_bam', 0):.2f} BAM
        </div>

        <div style="margin-top: 10px; padding: 10px; background-color: #fff3cd; border-radius: 5px;">
            <strong>{source_name} Subtotal:</strong> {source_total:.2f} BAM
        </div>
    </div>
"""

            # If multiple sources, add combined summary
            if len(sources) > 1:
                report += f"""
    <div class="section">
        <div class="section-title">💵 COMBINED BANK BALANCE</div>
"""
                for source in sources:
                    source_name = source.get('source_name', 'Unknown')
                    source_total = source.get('total_balance_bam', 0)
                    report += f"""
        <div class="balance-row">
            <span class="balance-label">{source_name}:</span>
            <span class="balance-value">{source_total:.2f} BAM</span>
        </div>
"""
                report += f"""
        <hr style="margin: 10px 0;">
        <div class="balance-row" style="font-size: 18px;">
            <span class="balance-label">GRAND TOTAL:</span>
            <span class="balance-value">{multi_account_info.get('total_balance_bam', 0):.2f} BAM</span>
        </div>
    </div>
"""
        else:
            # Single-source mode (backward compatibility)
            report += f"""
    <div class="section">
        <div class="section-title">📊 MULTI-ACCOUNT BALANCES</div>
        <div class="balance-row">
            <span class="balance-label">BAM Account ({self.BAM_ACCOUNT}):</span>
            <span class="balance-value">{bam_info.get('balance', 0):.2f} BAM</span>
        </div>
        <div style="margin-left: 20px; color: #666; font-size: 14px;">
            Source File: {bam_info.get('pdf_filename', 'none')}
            • Status: {'✅ Found' if bam_info.get('found') else '❌ Not Found'}
        </div>

        <div class="balance-row" style="margin-top: 15px;">
            <span class="balance-label">EUR Account ({self.EUR_ACCOUNT}):</span>
            <span class="balance-value">{eur_info.get('balance', 0):.2f} EUR</span>
        </div>
        <div style="margin-left: 20px; color: #666; font-size: 14px;">
            Source File: {eur_info.get('pdf_filename', 'none')}
            • Status: {'✅ Found' if eur_info.get('found') else '❌ Not Found'}
        </div>

        <div style="margin-top: 15px; padding: 10px; background-color: #e8f5e8; border-radius: 5px;">
            <strong>EUR to BAM Conversion:</strong><br>
            {eur_info.get('balance', 0):.2f} EUR × {multi_account_info.get('conversion_rate', self.EUR_TO_BAM_RATE)} = {eur_info.get('balance_bam', 0):.2f} BAM
        </div>
    </div>
"""

        report += f"""

    <div class="section">
        <div class="section-title">💰 TOTAL ASSETS CALCULATION</div>
        <div class="calculation">
            <div class="balance-row">
                <span>Combined Bank Balance:</span>
                <span class="balance-value">{analysis_result['bank_balance']:.2f} BAM</span>
            </div>
            <div class="balance-row">
                <span>Additional Assets:</span>
                <span class="balance-value">+ {analysis_result['additional_assets']:.2f} BAM</span>
            </div>
            <hr style="margin: 10px 0;">
            <div class="balance-row" style="font-size: 18px;">
                <span class="balance-label">TOTAL ASSETS:</span>
                <span class="balance-value">{analysis_result['total_assets']:.2f} BAM</span>
            </div>
        </div>
        <div style="color: #666; font-size: 14px;">
            Statement Period: {multi_account_info.get('period_end', 'Unknown')}
        </div>
    </div>

    <div class="section">
        <div class="section-title">📏 NISAB ANALYSIS</div>
        <div class="balance-row">
            <span>Nisab Threshold:</span>
            <span class="balance-value">{analysis_result['nisab_threshold']:.2f} BAM</span>
        </div>
        <div class="balance-row">
            <span>Above Nisab:</span>
            <span class="{'status-yes' if analysis_result['above_nisab'] else 'status-no'}">
                {'✅ YES' if analysis_result['above_nisab'] else '❌ NO'}
            </span>
        </div>
        <div class="balance-row">
            <span>Consecutive Months Above Nisab:</span>
            <span class="balance-value">{analysis_result['consecutive_months_above_nisab']} / 12</span>
        </div>
        
        <!-- Progress bar for 12-month requirement -->
        <div style="margin: 15px 0;">
            <div style="font-weight: bold; margin-bottom: 5px;">Progress to Zakat Requirement:</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {min(100, (analysis_result['consecutive_months_above_nisab'] / 12) * 100):.1f}%;"></div>
            </div>
            <div style="text-align: center; margin-top: 5px; font-size: 14px;">
                {analysis_result['consecutive_months_above_nisab']} of 12 months completed
            </div>
        </div>
        
        <div class="balance-row">
            <span>Hijri Year Complete:</span>
            <span class="{'status-yes' if analysis_result['hijri_year_complete'] else 'status-no'}">
                {'✅ YES' if analysis_result['hijri_year_complete'] else '❌ NO'}
            </span>
        </div>
        <div style="color: #666; font-size: 14px; margin-top: 10px;">
            Nisab Source: {nisab_source}
        </div>
    </div>

    <div class="section">
        <div class="section-title">🕌 ZAKAT CALCULATION</div>
        <div class="calculation">
            <div class="balance-row" style="font-size: 18px;">
                <span class="balance-label">Zakat Due:</span>
                <span class="{'status-yes' if analysis_result['zakat_due'] else 'status-no'}">
                    {'✅ YES' if analysis_result['zakat_due'] else '❌ NO'}
                </span>
            </div>
            <div class="balance-row" style="font-size: 18px;">
                <span class="balance-label">Zakat Amount:</span>
                <span class="balance-value">{analysis_result['zakat_amount']:.2f} BAM</span>
            </div>
        </div>
    </div>
"""

        # Add payment instructions if zakat is due
        if analysis_result.get('zakat_due', False):
            report += """
    <div class="section" style="background-color: #fff3cd; border-left: 4px solid #f39c12;">
        <div class="section-title" style="color: #f39c12;">📝 HOW TO MARK ZAKAT AS PAID</div>
        <p style="margin-bottom: 15px;">Once you have paid your zakat, record the payment to reset the 12-month cycle:</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
            <strong>Option 1: GitHub Actions (Easiest)</strong>
            <ol style="margin: 10px 0; padding-left: 20px;">
                <li>Go to your repository's <strong>Actions</strong> tab</li>
                <li>Click <strong>Zakat Monitor</strong> workflow</li>
                <li>Click <strong>Run workflow</strong> button</li>
                <li>Check the box: <strong>"Mark zakat as paid"</strong></li>
                <li>Click <strong>Run workflow</strong></li>
            </ol>
        </div>

        <div style="background-color: white; padding: 15px; border-radius: 5px;">
            <strong>Option 2: Command Line</strong>
            <p style="margin: 10px 0; font-family: monospace; background-color: #f5f5f5; padding: 10px; border-radius: 3px;">
                python zakat_monitor.py --mark-paid
            </p>
            <p style="margin: 5px 0; color: #666; font-size: 14px;">
                Forgot to mark it? Backdate the payment:<br>
                <span style="font-family: monospace; background-color: #f5f5f5; padding: 5px; border-radius: 3px;">
                    python zakat_monitor.py --mark-paid --date 15.01.2025
                </span>
            </p>
        </div>

        <p style="margin-top: 15px; color: #666; font-size: 14px;">
            ℹ️ After marking as paid, the counter resets to "0 of 12 months" and starts counting again.
        </p>
    </div>
"""

        report += f"""
    <div class="section">
        <div class="section-title">ℹ️ REFERENCE INFORMATION</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
            <div>
                <strong>Islamic Requirement:</strong><br>
                12 consecutive months above nisab threshold
            </div>
            <div>
                <strong>Zakat Rate:</strong><br>
                2.5% of total assets when due
            </div>
            <div>
                <strong>EUR to BAM Rate:</strong><br>
                {multi_account_info.get('conversion_rate', self.EUR_TO_BAM_RATE)} (fixed)
            </div>
            <div>
                <strong>History Tracking:</strong><br>
                ✅ {len(self.balance_history)} months recorded
            </div>
        </div>
    </div>

    <div class="footer">
        <p><strong>⚠️ IMPORTANT DISCLAIMER:</strong></p>
        <p>This analysis is for informational purposes only. Please consult with a qualified Islamic scholar for final zakat determination. Please verify the current nisab value at <a href="https://zekat.ba">zekat.ba</a> before making final decisions.</p>
        <p>Generated by Automated Zakat Monitoring System • Balance History: {len(self.balance_history)} months tracked</p>
    </div>
</body>
</html>
"""
        
        return report

    def send_email_report(self, report: str, statement_period: str, analysis_result: Dict):
        """Send HTML email report with proper styling and conditional subject line"""
        try:
            logger.info("Attempting to send email report...")
            
            # Check if email configuration is complete
            if not all([
                self.config['email']['username'],
                self.config['email']['password'],
                self.config['email']['sender_email'],
                self.config['email']['recipient_email']
            ]):
                logger.error("Email configuration incomplete - missing required email settings")
                return
            
            # Import email libraries for proper MIME handling
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.header import Header
            
            # Extract month/year from statement period (format: DD.MM.YYYY)
            try:
                parts = statement_period.split('.')
                if len(parts) == 3:
                    month = parts[1]
                    year = parts[2]
                    base_subject = f"Zekat Report - {month}/{year}"
                else:
                    base_subject = f"Zekat Report - {datetime.now().strftime('%m/%Y')}"
            except Exception:
                base_subject = f"Zekat Report - {datetime.now().strftime('%m/%Y')}"
            
            # ADD CONDITIONAL SUBJECT PREFIX
            subject_prefix = ""
            if analysis_result.get('zakat_due', False):
                subject_prefix = "Zekat Due Now - "
            
            subject = f"{subject_prefix}{base_subject}"
            
            # Create proper MIME message with UTF-8 encoding
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']['sender_email']
            msg['To'] = self.config['email']['recipient_email']
            msg['Subject'] = Header(subject, 'utf-8')
            
            # Add the report as HTML with UTF-8 encoding
            html_part = MIMEText(report, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Connect to SMTP server
            logger.info(f"Connecting to SMTP server: {self.config['email']['smtp_server']}:{self.config['email']['smtp_port']}")
            server = smtplib.SMTP(self.config['email']['smtp_server'], 
                                self.config['email']['smtp_port'], timeout=20)
            smtp_context = ssl.create_default_context()
            try:
                import certifi
                smtp_context.load_verify_locations(certifi.where())
            except (ImportError, OSError):
                pass
            server.starttls(context=smtp_context)
            
            logger.info("Logging in to email server...")
            server.login(self.config['email']['username'], 
                        self.config['email']['password'])
            
            logger.info(f"Sending HTML email with subject: {subject}")
            server.sendmail(self.config['email']['sender_email'],
                          [self.config['email']['recipient_email']], 
                          msg.as_string())
            
            server.quit()
            logger.info("HTML email report sent successfully!")
            
        except UnicodeEncodeError as e:
            logger.error(f"Email encoding error: {e}")
            logger.error("This usually means special characters in the report need proper UTF-8 handling")
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed: {e}")
            logger.error("Check your EMAIL_PASSWORD - you may need a Gmail App Password")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def trigger_github_action(self, report_data: Dict):
        """Create GitHub Actions artifact"""
        try:
            artifact_data = {
                'report': report_data,
                'timestamp': datetime.now().isoformat(),
                'encrypted': bool(self.cipher_suite),
                'multi_account': True
            }
            
            with open('zakat_report_artifact.json', 'w') as f:
                json.dump(artifact_data, f, indent=2)
            
            logger.info("GitHub Actions artifact created")
            
        except Exception as e:
            logger.error(f"Failed to create GitHub artifact: {e}")

    def run_analysis(self):
        """Main analysis workflow for multi-account setup"""
        try:
            logger.info("Starting Multi-Account Zakat Nisab analysis...")
            
            # Check configuration
            required_vars = ['EMAIL_USERNAME', 'EMAIL_PASSWORD']
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            if missing_vars:
                logger.error(f"Missing required environment variables: {missing_vars}")
                self._generate_status_report(f"Missing configuration: {missing_vars}")
                raise RuntimeError(f"Missing required email configuration: {', '.join(missing_vars)}")
            
            # Process all email sources
            combined_balance_info = self._process_all_sources()
            
            if not combined_balance_info or combined_balance_info.get('total_balance_bam', 0) == 0:
                logger.error("Could not extract balance information from either account")
                self._generate_status_report("Could not extract balance information from either account")
                # Build diagnostic detail for troubleshooting
                diag = "; ".join(getattr(self, '_source_diagnostics', []) or ["no sources processed"])
                raise RuntimeError(
                    "Could not extract balance information. "
                    f"Source details: [{diag}]. "
                    "Check that your email contains ProCredit Bank PDF statements "
                    "and that your BAM/EUR account numbers are correct."
                )
            else:
                logger.info("Successfully extracted multi-account balance information")
            
            # Get current nisab threshold (no gold API needed)
            nisab_threshold, nisab_source = self.calculate_nisab_threshold()
            
            # Convert dates to Hijri
            if combined_balance_info.get('period_end'):
                current_date = self.convert_gregorian_to_hijri(combined_balance_info['period_end'])
            else:
                # Fallback to current date
                current_date_str = datetime.now().strftime('%d.%m.%Y')
                current_date = self.convert_gregorian_to_hijri(current_date_str)
                logger.warning(f"Using current date as fallback: {current_date_str}")
            
            # Check Hijri year threshold using combined balance
            bank_balance = combined_balance_info['total_balance_bam']
            total_balance_with_assets = bank_balance + self.config['additional_assets']
            
            analysis_result = self.check_hijri_year_threshold(
                total_balance_with_assets, nisab_threshold, current_date, bank_balance
            )
            
            # Save updated history
            self._save_balance_history()
            
            # Generate comprehensive HTML report
            report = self.generate_encrypted_report(
                analysis_result, nisab_source, combined_balance_info
            )
            
            # Send email report with conditional subject line
            try:
                statement_period = combined_balance_info.get('period_end', datetime.now().strftime('%d.%m.%Y'))
                logger.debug(f"Sending email report for period '{statement_period}', report length {len(report)}")
                self.send_email_report(report, statement_period, analysis_result)
            except Exception as e:
                logger.error(f"Email sending failed: {e}")
            
            # Create GitHub Actions artifact
            # Sanitize artifact payload: exclude PII like account numbers and filenames
            sanitized_multi = {
                'bam_account': {
                    'balance': combined_balance_info['bam_account'].get('balance', 0.0),
                    'balance_bam': combined_balance_info['bam_account'].get('balance_bam', 0.0),
                    'found': combined_balance_info['bam_account'].get('found', False),
                },
                'eur_account': {
                    'balance': combined_balance_info['eur_account'].get('balance', 0.0),
                    'balance_bam': combined_balance_info['eur_account'].get('balance_bam', 0.0),
                    'found': combined_balance_info['eur_account'].get('found', False),
                },
                'total_balance_bam': combined_balance_info.get('total_balance_bam', 0.0),
                'period_end': combined_balance_info.get('period_end')
            }

            # Include per-source breakdowns if available
            if 'sources' in combined_balance_info:
                sanitized_multi['sources'] = []
                for source in combined_balance_info['sources']:
                    sanitized_source = {
                        'source_name': source.get('source_name'),
                        'bam_account': {
                            'balance': source['bam_account'].get('balance', 0.0),
                            'balance_bam': source['bam_account'].get('balance_bam', 0.0),
                            'found': source['bam_account'].get('found', False),
                        },
                        'eur_account': {
                            'balance': source['eur_account'].get('balance', 0.0),
                            'balance_bam': source['eur_account'].get('balance_bam', 0.0),
                            'found': source['eur_account'].get('found', False),
                        },
                        'total_balance_bam': source.get('total_balance_bam', 0.0),
                        'period_end': source.get('period_end')
                    }
                    sanitized_multi['sources'].append(sanitized_source)
            enhanced_report_data = analysis_result.copy()
            enhanced_report_data['multi_account_details'] = sanitized_multi
            self.trigger_github_action(enhanced_report_data)

            # Include per-source breakdown in result
            source_details = []
            for src in combined_balance_info.get('sources', [combined_balance_info]):
                source_details.append({
                    'source_name': src.get('source_name', 'Primary'),
                    'bam_balance': src.get('bam_account', {}).get('balance', 0.0),
                    'bam_balance_in_bam': src.get('bam_account', {}).get('balance_bam', 0.0),
                    'eur_balance': src.get('eur_account', {}).get('balance', 0.0),
                    'eur_balance_in_bam': src.get('eur_account', {}).get('balance_bam', 0.0),
                    'total_bam': src.get('total_balance_bam', 0.0),
                    'period_end': src.get('period_end', ''),
                })
            analysis_result['sources'] = source_details

            # Include date information for history tracking
            analysis_result['gregorian_date'] = current_date.get('gregorian_date', '')
            hijri_parts = [current_date.get('hijri_day'), current_date.get('hijri_month'), current_date.get('hijri_year')]
            if all(hijri_parts):
                analysis_result['hijri_date'] = f"{hijri_parts[0]}/{hijri_parts[1]}/{hijri_parts[2]}"
            else:
                analysis_result['hijri_date'] = ''

            logger.info("Multi-account Zakat analysis completed successfully")
            return analysis_result

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            self._generate_status_report(f"Analysis failed: {str(e)}")
            raise

    def _generate_status_report(self, message: str):
        """Generate a status report when full analysis isn't possible"""
        try:
            status_report = {
                'status': 'error',
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'multi_account': True,
                'accounts': {
                    'bam_account': self.BAM_ACCOUNT,
                    'eur_account': self.EUR_ACCOUNT,
                    'conversion_rate': self.EUR_TO_BAM_RATE,
                    'company_configured': len(self.email_sources) > 1
                },
                'configuration_check': {
                    'email_configured': bool(os.getenv('EMAIL_USERNAME')),
                    'encryption_configured': bool(os.getenv('ZAKAT_ENCRYPTION_KEY')),
                    'nisab_fallback': os.getenv('NISAB_FALLBACK_BAM', 'not_set')
                }
            }
            
            with open('zakat_report_artifact.json', 'w') as f:
                json.dump(status_report, f, indent=2)
                
            logger.info(f"Status report created: {message}")
            
        except Exception as e:
            logger.error(f"Failed to create status report: {e}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Zakat Monitor - Track zakat eligibility')
    parser.add_argument('--mark-paid', action='store_true',
                        help='Mark zakat as paid and reset the cycle')
    parser.add_argument('--date', type=str, metavar='DD.MM.YYYY',
                        help='Payment date (optional, defaults to today). Format: DD.MM.YYYY')

    args = parser.parse_args()

    zm = ZakatMonitor()

    # Check if --mark-paid flag or MARK_PAID env var is set
    mark_paid_flag = args.mark_paid or os.getenv('MARK_PAID', '').lower() in ('true', '1', 'yes')

    if mark_paid_flag:
        # Record payment and exit
        zm.record_zakat_payment(payment_date=args.date)
    else:
        # Run normal analysis
        zm.run_analysis()