"""
Pydantic schemas for API request/response models
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


# --- New multi-source schemas ---

class AccountPair(BaseModel):
    """A BAM/EUR bank account pair"""
    bam_account: str = Field(min_length=1)
    eur_account: str = Field(min_length=1)


class EmailSource(BaseModel):
    """An email source with IMAP credentials and associated account pairs"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str = Field(default="")
    email: EmailStr
    password: str = Field(min_length=1)
    imap_server: str = Field(default="imap.gmail.com")
    imap_port: int = Field(default=993)
    account_pairs: List[AccountPair] = Field(min_length=1)


class ReportDeliveryConfig(BaseModel):
    """SMTP configuration for sending zakat reports"""
    smtp_server: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    username: EmailStr
    password: str = Field(min_length=1)
    sender_email: EmailStr
    recipient_email: EmailStr


class YearProgressOverride(BaseModel):
    """Manual override for year progress when migrating"""
    enabled: bool = False
    months_above_nisab: int = Field(default=0, ge=0, le=11)
    as_of_hijri_date: str = Field(default="")


# --- Setup schemas (updated) ---

class SetupRequest(BaseModel):
    """Initial setup request with multi-source support"""
    master_password: str = Field(min_length=8)
    email_sources: List[EmailSource] = Field(min_length=1)
    report_delivery: ReportDeliveryConfig
    encryption_key: str
    year_progress_override: Optional[YearProgressOverride] = None
    additional_assets: float = Field(default=0.0, ge=0)
    nisab_fallback_bam: float = Field(default=24624.0, gt=0)


class SetupResponse(BaseModel):
    """Setup response"""
    success: bool
    message: str


# --- Settings schemas (updated) ---

class SettingsResponse(BaseModel):
    """Current settings with masked credentials"""
    email_sources: List[Dict[str, Any]]
    report_delivery: Dict[str, Any]
    year_progress_override: Optional[Dict[str, Any]] = None
    additional_assets: float
    nisab_fallback_bam: float
    has_encryption_key: bool


class SettingsUpdateRequest(BaseModel):
    """Update settings request"""
    master_password: str
    email_sources: Optional[List[EmailSource]] = None
    report_delivery: Optional[ReportDeliveryConfig] = None
    year_progress_override: Optional[YearProgressOverride] = None
    additional_assets: Optional[float] = Field(default=None, ge=0)
    nisab_fallback_bam: Optional[float] = Field(default=None, gt=0)


class SettingsUpdateResponse(BaseModel):
    """Update settings response"""
    success: bool
    message: str


# --- Email source CRUD schemas ---

class AddEmailSourceRequest(BaseModel):
    """Add a new email source"""
    master_password: str
    email_source: EmailSource


class AddEmailSourceResponse(BaseModel):
    """Add email source response"""
    success: bool
    message: str
    source_id: str


class UpdateEmailSourceRequest(BaseModel):
    """Update an existing email source"""
    master_password: str
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    account_pairs: Optional[List[AccountPair]] = None


class DeleteEmailSourceRequest(BaseModel):
    """Delete an email source"""
    master_password: str


# --- Year progress schemas ---

class YearProgressUpdateRequest(BaseModel):
    """Update year progress override"""
    master_password: str
    enabled: bool
    months_above_nisab: int = Field(default=0, ge=0, le=11)
    as_of_hijri_date: str = Field(default="")


class YearProgressUpdateResponse(BaseModel):
    """Year progress update response"""
    success: bool
    message: str


# --- Restart setup schemas ---

class RestartSetupRequest(BaseModel):
    """Request to get current config for restart"""
    master_password: str


class RestartSetupResponse(BaseModel):
    """Returns full config for pre-filling wizard"""
    success: bool
    config: Dict[str, Any]


# --- Status schemas ---

class ZakatStatusResponse(BaseModel):
    """Current zakat monitoring status"""
    initialized: bool
    bank_balance: Optional[float] = None
    additional_assets: Optional[float] = None
    total_assets: Optional[float] = None
    nisab_threshold: Optional[float] = None
    above_nisab: Optional[bool] = None
    consecutive_months_above_nisab: Optional[int] = None
    hijri_year_complete: Optional[bool] = None
    zakat_due: Optional[bool] = None
    zakat_amount: Optional[float] = None
    last_check: Optional[str] = None


# --- Analysis schemas ---

class AnalyzeRequest(BaseModel):
    """Trigger analysis request"""
    master_password: str


class AnalyzeResponse(BaseModel):
    """Analysis trigger response"""
    success: bool
    message: str
    task_id: Optional[str] = None


class AnalysisProgressEvent(BaseModel):
    """SSE event for analysis progress"""
    event: str
    message: str
    progress: Optional[int] = None
    data: Optional[Dict[str, Any]] = None


class AnalysisResult(BaseModel):
    """Analysis result"""
    bank_balance: float
    additional_assets: float
    total_assets: float
    nisab_threshold: float
    above_nisab: bool
    consecutive_months_above_nisab: int
    hijri_year_complete: bool
    zakat_due: bool
    zakat_amount: float
    timestamp: str


# --- History schemas ---

class BalanceHistoryEntry(BaseModel):
    """Single balance history entry"""
    hijri_date: str
    gregorian_date: str
    balance_bam: float
    balance_eur: float
    total_bam: float
    nisab_threshold: float
    above_nisab: bool
    consecutive_months: int


class HistoryResponse(BaseModel):
    """Balance history response"""
    entries: List[BalanceHistoryEntry]
    total_count: int


# --- Zakat Payment schemas ---

class MarkPaidRequest(BaseModel):
    """Mark zakat as paid request"""
    master_password: str
    amount: float = Field(gt=0)
    hijri_date: str


class MarkPaidResponse(BaseModel):
    """Mark paid response"""
    success: bool
    message: str


# --- Nisab schemas ---

class NisabResponse(BaseModel):
    """Current nisab threshold"""
    nisab_bam: float
    source: str
    fetched_at: Optional[str] = None


# --- Health and Info schemas ---

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    version: str


class ApiInfoResponse(BaseModel):
    """API information"""
    message: str
    version: str
    status: str
    endpoints: List[str]
