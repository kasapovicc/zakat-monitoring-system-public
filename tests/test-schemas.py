"""Tests for Pydantic schemas"""
import pytest
from pydantic import ValidationError
from app.api.schemas import (
    AccountPair,
    EmailSource,
    ReportDeliveryConfig,
    YearProgressOverride,
    SetupRequest,
)


class TestAccountPair:
    def test_valid_account_pair(self):
        pair = AccountPair(bam_account="1234567890", eur_account="0987654321")
        assert pair.bam_account == "1234567890"
        assert pair.eur_account == "0987654321"

    def test_empty_bam_rejected(self):
        with pytest.raises(ValidationError):
            AccountPair(bam_account="", eur_account="123")

    def test_empty_eur_rejected(self):
        with pytest.raises(ValidationError):
            AccountPair(bam_account="123", eur_account="")


class TestEmailSource:
    def test_valid_email_source(self):
        source = EmailSource(
            email="test@gmail.com",
            password="apppass",
            account_pairs=[
                AccountPair(bam_account="111", eur_account="222")
            ],
        )
        assert source.email == "test@gmail.com"
        assert source.id is not None  # auto-generated UUID
        assert source.imap_server == "imap.gmail.com"
        assert source.imap_port == 993
        assert len(source.account_pairs) == 1

    def test_empty_account_pairs_rejected(self):
        with pytest.raises(ValidationError):
            EmailSource(
                email="test@gmail.com",
                password="apppass",
                account_pairs=[],
            )

    def test_multiple_account_pairs(self):
        source = EmailSource(
            email="test@gmail.com",
            password="apppass",
            account_pairs=[
                AccountPair(bam_account="111", eur_account="222"),
                AccountPair(bam_account="333", eur_account="444"),
            ],
        )
        assert len(source.account_pairs) == 2


class TestReportDeliveryConfig:
    def test_valid_report_delivery(self):
        config = ReportDeliveryConfig(
            username="sender@gmail.com",
            password="apppass",
            sender_email="sender@gmail.com",
            recipient_email="recipient@gmail.com",
        )
        assert config.smtp_server == "smtp.gmail.com"
        assert config.smtp_port == 587

    def test_missing_recipient_rejected(self):
        with pytest.raises(ValidationError):
            ReportDeliveryConfig(
                username="sender@gmail.com",
                password="apppass",
                sender_email="sender@gmail.com",
                # missing recipient_email
            )


class TestYearProgressOverride:
    def test_valid_override(self):
        override = YearProgressOverride(
            enabled=True,
            months_above_nisab=8,
            as_of_hijri_date="15/06/1446",
        )
        assert override.months_above_nisab == 8

    def test_months_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            YearProgressOverride(
                enabled=True,
                months_above_nisab=12,
                as_of_hijri_date="15/06/1446",
            )

    def test_negative_months_rejected(self):
        with pytest.raises(ValidationError):
            YearProgressOverride(
                enabled=True,
                months_above_nisab=-1,
                as_of_hijri_date="15/06/1446",
            )

    def test_disabled_override(self):
        override = YearProgressOverride(enabled=False)
        assert override.months_above_nisab == 0
        assert override.as_of_hijri_date == ""


class TestSetupRequestNewSchema:
    def test_valid_setup_request(self):
        req = SetupRequest(
            master_password="strongpass123",
            email_sources=[
                EmailSource(
                    email="test@gmail.com",
                    password="apppass",
                    account_pairs=[
                        AccountPair(bam_account="111", eur_account="222")
                    ],
                )
            ],
            report_delivery=ReportDeliveryConfig(
                username="sender@gmail.com",
                password="apppass",
                sender_email="sender@gmail.com",
                recipient_email="recipient@gmail.com",
            ),
            encryption_key="dGVzdGtleQ==",
        )
        assert len(req.email_sources) == 1

    def test_empty_email_sources_rejected(self):
        with pytest.raises(ValidationError):
            SetupRequest(
                master_password="strongpass123",
                email_sources=[],
                report_delivery=ReportDeliveryConfig(
                    username="sender@gmail.com",
                    password="apppass",
                    sender_email="sender@gmail.com",
                    recipient_email="recipient@gmail.com",
                ),
                encryption_key="dGVzdGtleQ==",
            )
