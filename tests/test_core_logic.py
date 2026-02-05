"""Tests for core logic functions in zakat_monitor.py"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from zakat_monitor import (
    parse_bosnian_number,
    parse_email_date,
    ZakatMonitor,
    ZAKAT_RATE,
    HIJRI_YEAR_MONTHS,
)


# --- parse_bosnian_number ---

class TestParseBosnianNumber:
    def test_simple_number(self):
        assert parse_bosnian_number('1.234,56') == 1234.56

    def test_large_number(self):
        assert parse_bosnian_number('12.345,67') == 12345.67

    def test_no_thousands_separator(self):
        assert parse_bosnian_number('234,56') == 234.56

    def test_zero(self):
        assert parse_bosnian_number('0,00') == 0.0

    def test_millions(self):
        assert parse_bosnian_number('1.234.567,89') == 1234567.89

    def test_single_digit(self):
        assert parse_bosnian_number('5,00') == 5.0

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_bosnian_number('abc')


# --- parse_email_date ---

class TestParseEmailDate:
    def test_rfc2822_format(self):
        result = parse_email_date('Mon, 1 Jul 2025 12:00:00 +0000')
        assert result.year == 2025
        assert result.month == 7
        assert result.day == 1

    def test_short_month_format(self):
        result = parse_email_date('15 Jun 2025')
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15

    def test_malformed_returns_epoch(self):
        result = parse_email_date('not a date')
        assert result == datetime(1970, 1, 1)

    def test_empty_string_returns_epoch(self):
        result = parse_email_date('')
        assert result == datetime(1970, 1, 1)


# --- Static validators ---

class TestValidateEmail:
    def test_valid_email(self):
        assert ZakatMonitor._validate_email('user@example.com') is True

    def test_invalid_email_no_at(self):
        assert ZakatMonitor._validate_email('userexample.com') is False

    def test_invalid_email_empty(self):
        assert ZakatMonitor._validate_email('') is False

    def test_invalid_email_no_domain(self):
        assert ZakatMonitor._validate_email('user@') is False

    def test_valid_email_with_dots(self):
        assert ZakatMonitor._validate_email('first.last@sub.domain.com') is True


class TestValidateDateFormat:
    def test_valid_date(self):
        assert ZakatMonitor._validate_date_format('31.01.2025') is True

    def test_invalid_format(self):
        assert ZakatMonitor._validate_date_format('2025-01-31') is False

    def test_empty(self):
        assert ZakatMonitor._validate_date_format('') is False

    def test_invalid_date_values(self):
        assert ZakatMonitor._validate_date_format('32.13.2025') is False

    def test_valid_leap_year(self):
        assert ZakatMonitor._validate_date_format('29.02.2024') is True

    def test_invalid_leap_year(self):
        assert ZakatMonitor._validate_date_format('29.02.2023') is False


class TestValidateBalance:
    def test_valid_balance(self):
        assert ZakatMonitor._validate_balance(1000.0) is True

    def test_zero(self):
        assert ZakatMonitor._validate_balance(0.0) is True

    def test_negative(self):
        assert ZakatMonitor._validate_balance(-1.0) is False

    def test_too_large(self):
        assert ZakatMonitor._validate_balance(200_000_000) is False

    def test_max_boundary(self):
        assert ZakatMonitor._validate_balance(100_000_000) is True

    def test_non_numeric(self):
        assert ZakatMonitor._validate_balance('abc') is False


# --- convert_gregorian_to_hijri ---

class TestConvertGregorianToHijri:
    def test_known_date(self, monitor):
        result = monitor.convert_gregorian_to_hijri('01.01.2025')
        assert 'hijri_year' in result
        assert 'hijri_month' in result
        assert 'hijri_day' in result
        assert result['gregorian_date'] == '01.01.2025'

    def test_invalid_date_returns_partial(self, monitor):
        result = monitor.convert_gregorian_to_hijri('invalid')
        assert result['gregorian_date'] == 'invalid'
        assert 'hijri_year' not in result


# --- check_hijri_year_threshold ---

class TestCheckHijriYearThreshold:
    def test_below_nisab(self, monitor):
        current_date = {'hijri_year': 1446, 'hijri_month': 6, 'gregorian_date': '01.01.2025'}
        result = monitor.check_hijri_year_threshold(
            total_assets=5000.0,
            nisab_threshold=16000.0,
            current_date=current_date,
            bank_balance=5000.0,
        )
        assert result['above_nisab'] is False
        assert result['zakat_due'] is False
        assert result['zakat_amount'] == 0

    def test_above_nisab_not_12_months(self, monitor):
        current_date = {'hijri_year': 1446, 'hijri_month': 6, 'gregorian_date': '01.01.2025'}
        result = monitor.check_hijri_year_threshold(
            total_assets=20000.0,
            nisab_threshold=16000.0,
            current_date=current_date,
            bank_balance=20000.0,
        )
        assert result['above_nisab'] is True
        assert result['consecutive_months_above_nisab'] == 1
        assert result['zakat_due'] is False

    def test_12_consecutive_months_triggers_zakat(self, monitor):
        # Simulate 11 months of history above nisab
        for i in range(11):
            monitor.balance_history.append({
                'balance': 20000.0,
                'nisab_threshold': 16000.0,
                'above_nisab': True,
                'hijri_year': 1446,
                'hijri_month': i + 1,
                'gregorian_date': f'{i+1:02d}.01.2025',
                'timestamp': f'2025-01-{i+1:02d}T00:00:00',
            })

        current_date = {'hijri_year': 1446, 'hijri_month': 12, 'gregorian_date': '12.01.2025'}
        result = monitor.check_hijri_year_threshold(
            total_assets=20000.0,
            nisab_threshold=16000.0,
            current_date=current_date,
            bank_balance=20000.0,
        )
        assert result['consecutive_months_above_nisab'] >= HIJRI_YEAR_MONTHS
        assert result['hijri_year_complete'] is True
        assert result['zakat_due'] is True
        assert result['zakat_amount'] == pytest.approx(20000.0 * ZAKAT_RATE)

    def test_gap_resets_consecutive_count(self, monitor):
        # 5 months above, 1 below, then current above
        for i in range(5):
            monitor.balance_history.append({
                'balance': 20000.0,
                'nisab_threshold': 16000.0,
                'above_nisab': True,
                'hijri_year': 1446,
                'hijri_month': i + 1,
                'gregorian_date': f'{i+1:02d}.01.2025',
                'timestamp': f'2025-01-{i+1:02d}T00:00:00',
            })
        # Gap: one month below nisab
        monitor.balance_history.append({
            'balance': 5000.0,
            'nisab_threshold': 16000.0,
            'above_nisab': False,
            'hijri_year': 1446,
            'hijri_month': 6,
            'gregorian_date': '06.01.2025',
            'timestamp': '2025-01-06T00:00:00',
        })

        current_date = {'hijri_year': 1446, 'hijri_month': 7, 'gregorian_date': '07.01.2025'}
        result = monitor.check_hijri_year_threshold(
            total_assets=20000.0,
            nisab_threshold=16000.0,
            current_date=current_date,
            bank_balance=20000.0,
        )
        assert result['consecutive_months_above_nisab'] == 1
        assert result['zakat_due'] is False

    def test_payment_resets_consecutive_count(self, monitor):
        """Test that a payment marker resets the consecutive count"""
        # 12 months above nisab
        for i in range(12):
            monitor.balance_history.append({
                'balance': 20000.0,
                'nisab_threshold': 16000.0,
                'above_nisab': True,
                'hijri_year': 1446,
                'hijri_month': i + 1,
                'gregorian_date': f'{i+1:02d}.01.2025',
                'timestamp': f'2025-01-{i+1:02d}T00:00:00',
            })

        # Payment marker
        monitor.balance_history.append({
            'type': 'zakat_paid',
            'timestamp': '2025-01-15T10:00:00',
            'gregorian_date': '15.01.2025',
        })

        # Two more months above nisab
        monitor.balance_history.append({
            'balance': 20000.0,
            'nisab_threshold': 16000.0,
            'above_nisab': True,
            'hijri_year': 1446,
            'hijri_month': 13,
            'gregorian_date': '16.01.2025',
            'timestamp': '2025-01-16T00:00:00',
        })

        current_date = {'hijri_year': 1446, 'hijri_month': 14, 'gregorian_date': '17.01.2025'}
        result = monitor.check_hijri_year_threshold(
            total_assets=20000.0,
            nisab_threshold=16000.0,
            current_date=current_date,
            bank_balance=20000.0,
        )

        # Should only count 2 months (after payment marker)
        assert result['consecutive_months_above_nisab'] == 2
        assert result['zakat_due'] is False

    def test_no_payment_marker_backward_compat(self, monitor):
        """Test that existing behavior works without payment markers"""
        # 12 months above nisab (no payment markers)
        for i in range(11):
            monitor.balance_history.append({
                'balance': 20000.0,
                'nisab_threshold': 16000.0,
                'above_nisab': True,
                'hijri_year': 1446,
                'hijri_month': i + 1,
                'gregorian_date': f'{i+1:02d}.01.2025',
                'timestamp': f'2025-01-{i+1:02d}T00:00:00',
            })

        current_date = {'hijri_year': 1446, 'hijri_month': 12, 'gregorian_date': '12.01.2025'}
        result = monitor.check_hijri_year_threshold(
            total_assets=20000.0,
            nisab_threshold=16000.0,
            current_date=current_date,
            bank_balance=20000.0,
        )

        # Should work as before - 12 consecutive months triggers zakat
        assert result['consecutive_months_above_nisab'] >= HIJRI_YEAR_MONTHS
        assert result['zakat_due'] is True

    def test_mark_paid_records_entry(self, monitor, tmp_path):
        """Test that record_zakat_payment() appends correct entry"""
        # Set up temporary history file
        monitor.history_file = tmp_path / "test_history.json"
        monitor.balance_history = []

        # Record payment with today's date
        monitor.record_zakat_payment()

        # Check that an entry was added
        assert len(monitor.balance_history) == 1
        entry = monitor.balance_history[0]
        assert entry['type'] == 'zakat_paid'
        assert 'timestamp' in entry
        assert 'gregorian_date' in entry

    def test_backdated_payment(self, monitor, tmp_path):
        """Test payment with past date"""
        # Set up temporary history file
        monitor.history_file = tmp_path / "test_history.json"
        monitor.balance_history = []

        # Record backdated payment
        monitor.record_zakat_payment(payment_date='15.01.2025')

        # Check entry
        assert len(monitor.balance_history) == 1
        entry = monitor.balance_history[0]
        assert entry['type'] == 'zakat_paid'
        assert entry['gregorian_date'] == '15.01.2025'
        assert '2025-01-15' in entry['timestamp']


# --- extract_balance_from_procredit_pdf ---

class TestExtractBalanceFromPDF:
    """Test PDF balance extraction with mocked PDF text."""

    def test_pattern1_six_column_table(self, monitor):
        pdf_text = "1.000,00 500,00 700,00 1.200,00 5 3"
        mock_page = MagicMock()
        mock_page.extract_text.return_value = pdf_text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader.is_encrypted = False

        with patch('zakat_monitor.PyPDF2.PdfReader', return_value=mock_reader):
            result = monitor.extract_balance_from_procredit_pdf(b'fake_pdf')

        assert result is not None
        assert result['starting_balance'] == 1000.0
        assert result['ending_balance'] == 1200.0

    def test_pattern3_fallback_krajnje_stanje(self, monitor):
        pdf_text = "Krajnje stanje: 15.678,90\nDatum od: 01.06.2025\n30.06.2025 Datum do"
        mock_page = MagicMock()
        mock_page.extract_text.return_value = pdf_text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader.is_encrypted = False

        with patch('zakat_monitor.PyPDF2.PdfReader', return_value=mock_reader):
            result = monitor.extract_balance_from_procredit_pdf(b'fake_pdf')

        assert result is not None
        assert result['ending_balance'] == 15678.90
        assert result['period_start'] == '01.06.2025'

    def test_no_balance_returns_none(self, monitor):
        pdf_text = "This PDF has no balance information at all."
        mock_page = MagicMock()
        mock_page.extract_text.return_value = pdf_text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader.is_encrypted = False

        with patch('zakat_monitor.PyPDF2.PdfReader', return_value=mock_reader):
            result = monitor.extract_balance_from_procredit_pdf(b'fake_pdf')

        assert result is None

    def test_corrupted_pdf_returns_none(self, monitor):
        import PyPDF2
        with patch('zakat_monitor.PyPDF2.PdfReader', side_effect=PyPDF2.errors.PdfReadError("bad")):
            result = monitor.extract_balance_from_procredit_pdf(b'fake_pdf')

        assert result is None


# --- Masking helpers ---

class TestMaskHelpers:
    def test_mask_account(self):
        assert ZakatMonitor._mask_account('1234567890') == '****7890'

    def test_mask_account_empty(self):
        assert ZakatMonitor._mask_account('') == '****'

    def test_mask_email(self):
        result = ZakatMonitor._mask_email('user@example.com')
        assert 'user' not in result or result.startswith('u***')
        assert '@' in result

    def test_mask_email_none(self):
        assert ZakatMonitor._mask_email(None) == '***@***'

    def test_mask_amount(self):
        assert ZakatMonitor._mask_amount(1234.56) == '***'


# --- Multi-source email support ---

class TestEmailSourceBuilding:
    """Test _build_email_sources() with various configurations."""

    def test_single_source_without_company_vars(self, monitor):
        """Should have 1 source (Personal) when company vars not set."""
        assert len(monitor.email_sources) == 1
        assert monitor.email_sources[0]['name'] == 'Personal'
        assert monitor.email_sources[0]['bam_account'] == '1234567890'
        assert monitor.email_sources[0]['eur_account'] == '0987654321'

    def test_dual_source_with_company_vars(self, monitor_with_company):
        """Should have 2 sources (Personal + Company) when all company vars set."""
        assert len(monitor_with_company.email_sources) == 2
        assert monitor_with_company.email_sources[0]['name'] == 'Personal'
        assert monitor_with_company.email_sources[1]['name'] == 'Company'
        assert monitor_with_company.email_sources[1]['bam_account'] == '1111111111'
        assert monitor_with_company.email_sources[1]['eur_account'] == '2222222222'

    def test_backward_compat_attributes(self, monitor_with_company):
        """Should preserve BAM_ACCOUNT/EUR_ACCOUNT from primary source."""
        assert monitor_with_company.BAM_ACCOUNT == '1234567890'
        assert monitor_with_company.EUR_ACCOUNT == '0987654321'


class TestProcessAllSources:
    """Test _process_all_sources() orchestrator."""

    def test_merges_two_sources(self, monitor_with_company):
        """Should merge results from personal and company sources."""
        # Mock the individual processing methods
        mock_mail = MagicMock()

        personal_result = {
            'bam_account': {'balance': 1000.0, 'balance_bam': 1000.0, 'found': True},
            'eur_account': {'balance': 500.0, 'balance_bam': 977.92, 'found': True},
            'total_balance_bam': 1977.92,
            'period_end': '31.12.2025',
        }

        company_result = {
            'bam_account': {'balance': 2000.0, 'balance_bam': 2000.0, 'found': True},
            'eur_account': {'balance': 1000.0, 'balance_bam': 1955.83, 'found': True},
            'total_balance_bam': 3955.83,
            'period_end': '31.12.2025',
        }

        with patch.object(monitor_with_company, 'connect_to_gmail', return_value=mock_mail):
            with patch.object(monitor_with_company, 'process_multi_account_statements') as mock_process:
                # Return different results for each source
                mock_process.side_effect = [personal_result, company_result]

                result = monitor_with_company._process_all_sources()

        assert result is not None
        assert 'sources' in result
        assert len(result['sources']) == 2
        assert result['sources'][0]['source_name'] == 'Personal'
        assert result['sources'][1]['source_name'] == 'Company'
        assert result['total_balance_bam'] == pytest.approx(5933.75)

    def test_single_source_fallback(self, monitor):
        """Should work with single source when company vars not set."""
        mock_mail = MagicMock()

        personal_result = {
            'bam_account': {'balance': 1000.0, 'balance_bam': 1000.0, 'found': True},
            'eur_account': {'balance': 500.0, 'balance_bam': 977.92, 'found': True},
            'total_balance_bam': 1977.92,
            'period_end': '31.12.2025',
        }

        with patch.object(monitor, 'connect_to_gmail', return_value=mock_mail):
            with patch.object(monitor, 'process_multi_account_statements', return_value=personal_result):
                result = monitor._process_all_sources()

        assert result is not None
        assert 'sources' in result
        assert len(result['sources']) == 1
        assert result['total_balance_bam'] == pytest.approx(1977.92)


class TestReportWithMultipleSources:
    """Test HTML report generation with multiple sources."""

    def test_report_contains_both_sources(self, monitor_with_company):
        """HTML report should have sections for Personal and Company accounts."""
        analysis_result = {
            'above_nisab': True,
            'zakat_due': False,
            'zakat_amount': 0,
            'consecutive_months_above_nisab': 1,
            'hijri_year_complete': False,
            'total_assets': 5000.0,
            'bank_balance': 5000.0,
            'additional_assets': 0,
            'nisab_threshold': 24624.0,
        }

        multi_account_info = {
            'sources': [
                {
                    'source_name': 'Personal',
                    'bam_account': {'balance': 1000.0, 'balance_bam': 1000.0, 'found': True, 'pdf_filename': 'test.pdf'},
                    'eur_account': {'balance': 500.0, 'balance_bam': 977.92, 'found': True, 'pdf_filename': 'test2.pdf'},
                    'total_balance_bam': 1977.92,
                    'period_end': '31.12.2025',
                },
                {
                    'source_name': 'Company',
                    'bam_account': {'balance': 2000.0, 'balance_bam': 2000.0, 'found': True, 'pdf_filename': 'test3.pdf'},
                    'eur_account': {'balance': 1000.0, 'balance_bam': 1955.83, 'found': True, 'pdf_filename': 'test4.pdf'},
                    'total_balance_bam': 3955.83,
                    'period_end': '31.12.2025',
                },
            ],
            'total_balance_bam': 5933.75,
            'period_end': '31.12.2025',
            'conversion_rate': 1.955830,
            'currency': 'BAM',
            'bam_account': {'balance': 1000.0, 'balance_bam': 1000.0, 'found': True},
            'eur_account': {'balance': 500.0, 'balance_bam': 977.92, 'found': True},
        }

        report = monitor_with_company.generate_encrypted_report(
            analysis_result, 'Official nisab', multi_account_info
        )

        assert 'PERSONAL ACCOUNTS' in report
        assert 'COMPANY ACCOUNTS' in report
        assert 'COMBINED BANK BALANCE' in report
        assert 'GRAND TOTAL' in report

    def test_single_source_backward_compat(self, monitor):
        """Single source mode should render traditional report."""
        analysis_result = {
            'above_nisab': True,
            'zakat_due': False,
            'zakat_amount': 0,
            'consecutive_months_above_nisab': 1,
            'hijri_year_complete': False,
            'total_assets': 2000.0,
            'bank_balance': 2000.0,
            'additional_assets': 0,
            'nisab_threshold': 24624.0,
        }

        multi_account_info = {
            'bam_account': {'balance': 1000.0, 'balance_bam': 1000.0, 'found': True, 'pdf_filename': 'test.pdf'},
            'eur_account': {'balance': 500.0, 'balance_bam': 977.92, 'found': True, 'pdf_filename': 'test2.pdf'},
            'total_balance_bam': 1977.92,
            'period_end': '31.12.2025',
            'conversion_rate': 1.955830,
            'currency': 'BAM',
        }

        report = monitor.generate_encrypted_report(
            analysis_result, 'Official nisab', multi_account_info
        )

        assert 'MULTI-ACCOUNT BALANCES' in report
        assert 'PERSONAL ACCOUNTS' not in report
        assert 'COMPANY ACCOUNTS' not in report


class TestBackwardCompatibility:
    """Ensure single-source mode works identically to before."""

    def test_initialization_without_company_vars(self, monitor):
        """Monitor should initialize successfully without company vars."""
        assert monitor.BAM_ACCOUNT == '1234567890'
        assert monitor.EUR_ACCOUNT == '0987654321'
        assert len(monitor.email_sources) == 1

    def test_methods_work_without_params(self, monitor):
        """Parameterized methods should work with defaults."""
        # These should not raise errors
        assert monitor.identify_account_from_filename('1234567890_2025-01-01.pdf') == 'BAM'
        assert monitor.identify_account_from_filename('0987654321_2025-01-01.pdf') == 'EUR'
