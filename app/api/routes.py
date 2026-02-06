"""
API routes for Zekat monitoring app
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from app.api.schemas import (
    SetupRequest, SetupResponse,
    SettingsResponse, SettingsUpdateRequest, SettingsUpdateResponse,
    ZakatStatusResponse,
    AnalyzeRequest, AnalyzeResponse,
    HistoryResponse, BalanceHistoryEntry,
    MarkPaidRequest, MarkPaidResponse,
    NisabResponse,
    HealthResponse, ApiInfoResponse,
    AddEmailSourceRequest, AddEmailSourceResponse,
    UpdateEmailSourceRequest,
    DeleteEmailSourceRequest,
    YearProgressUpdateRequest, YearProgressUpdateResponse,
    RestartSetupRequest, RestartSetupResponse,
)
from app.storage.config import ConfigStorage
from app.storage.history import HistoryStorage
from app.adapter import ZakatMonitorAdapter

# Initialize router
router = APIRouter()

# Global state for analysis progress (in production, use Redis or similar)
analysis_progress = {
    "status": "idle",  # idle, running, completed, error
    "message": "",
    "progress": 0,
    "result": None
}

# Persist last analysis result to disk so it survives app restarts
_RESULT_FILE = Path.home() / "Library" / "Application Support" / "Zekat" / "last_result.json"


def _save_analysis_result(result: dict):
    """Save last analysis result to disk."""
    try:
        _RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_RESULT_FILE, 'w') as f:
            json.dump(result, f)
    except Exception as e:
        logger.warning(f"Could not persist analysis result: {e}")


def _load_analysis_result() -> dict | None:
    """Load last analysis result from disk."""
    try:
        if _RESULT_FILE.exists():
            with open(_RESULT_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load persisted analysis result: {e}")
    return None


# Helper functions

def get_config_storage() -> ConfigStorage:
    """Get ConfigStorage instance"""
    return ConfigStorage()


def get_adapter_from_config(master_password: str) -> ZakatMonitorAdapter:
    """
    Load config and create adapter instance.

    Raises:
        HTTPException: If config doesn't exist or password is wrong
    """
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration not found. Please complete setup first."
        )

    try:
        config = config_storage.load_config(master_password)
        adapter = ZakatMonitorAdapter(config)
        adapter.initialize()
        return adapter
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading configuration: {e}")


def mask_email(email: Optional[str]) -> str:
    """Mask email for display"""
    if not email:
        return "***@***"
    local, _, domain = email.partition('@')
    return f"{local[0]}***@{domain}" if local else "***@***"


def mask_account(account: Optional[str]) -> str:
    """Mask account number for display"""
    if not account or len(account) < 4:
        return "****"
    return f"****{account[-4:]}"


# Root and Health Endpoints

@router.get("/", response_model=ApiInfoResponse)
async def root():
    """API root with information"""
    return ApiInfoResponse(
        message="Zekat Monitor API",
        version="0.1.0",
        status="running",
        endpoints=[
            "GET /health",
            "GET /api/status",
            "POST /api/setup",
            "GET /api/settings",
            "PUT /api/settings",
            "POST /api/analyze",
            "GET /api/analyze/progress",
            "POST /api/mark-paid",
            "GET /api/history",
            "GET /api/nisab"
        ]
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="zekat-monitor",
        version="0.1.0"
    )


# Setup Endpoint

@router.post("/api/setup", response_model=SetupResponse)
async def setup(request: SetupRequest):
    """
    Initial setup - save encrypted configuration.
    Also used for restart-setup (overwrites existing config).
    """
    config_storage = get_config_storage()

    # Build config dictionary from new multi-source structure
    config = {
        'email_sources': [source.model_dump() for source in request.email_sources],
        'report_delivery': request.report_delivery.model_dump(),
        'encryption_key': request.encryption_key,
        'additional_assets': request.additional_assets,
        'nisab_fallback_bam': request.nisab_fallback_bam,
    }

    if request.year_progress_override:
        config['year_progress_override'] = request.year_progress_override.model_dump()

    try:
        config_storage.save_config(config, request.master_password)
        return SetupResponse(success=True, message="Configuration saved successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {e}")


# Status Endpoint

@router.get("/api/status", response_model=ZakatStatusResponse)
async def get_status():
    """
    Get current zakat monitoring status.
    Returns basic status without requiring password (for dashboard display).
    """
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        return ZakatStatusResponse(
            initialized=False
        )

    # For now, return that it's initialized but no data
    # In a full implementation, we'd load cached status or last analysis result
    return ZakatStatusResponse(
        initialized=True,
        last_check=None
    )


# Settings Endpoints

@router.get("/api/settings")
async def get_settings():
    """
    Get current settings with masked credentials.
    Note: This returns unprotected info. Sensitive data is masked.
    """
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration not found. Please complete setup first."
        )

    # Return masked settings (no password needed for display)
    return {
        "configured": True,
        "message": "Use GET /api/settings/full with master_password to view full settings"
    }


@router.get("/api/settings/full")
async def get_settings_full(master_password: str):
    """
    Get current settings with masked credentials.
    Requires master password to decrypt config.
    """
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration not found. Please complete setup first."
        )

    try:
        config = config_storage.load_config(master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Mask sensitive fields
    masked_sources = []
    for source in config.get('email_sources', []):
        masked_pairs = []
        for pair in source.get('account_pairs', []):
            masked_pairs.append({
                'bam_account': mask_account(pair.get('bam_account')),
                'eur_account': mask_account(pair.get('eur_account')),
            })
        masked_sources.append({
            'id': source.get('id', ''),
            'label': source.get('label', ''),
            'email': mask_email(source.get('email')),
            'password': '********',
            'imap_server': source.get('imap_server', 'imap.gmail.com'),
            'imap_port': source.get('imap_port', 993),
            'account_pairs': masked_pairs,
        })

    rd = config.get('report_delivery', {})
    masked_delivery = {
        'smtp_server': rd.get('smtp_server', 'smtp.gmail.com'),
        'smtp_port': rd.get('smtp_port', 587),
        'username': mask_email(rd.get('username')),
        'password': '********',
        'sender_email': mask_email(rd.get('sender_email')),
        'recipient_email': mask_email(rd.get('recipient_email')),
    }

    return {
        'success': True,
        'data': {
            'email_sources': masked_sources,
            'report_delivery': masked_delivery,
            'year_progress_override': config.get('year_progress_override'),
            'additional_assets': config.get('additional_assets', 0.0),
            'nisab_fallback_bam': config.get('nisab_fallback_bam', 24624.0),
            'has_encryption_key': bool(config.get('encryption_key')),
        }
    }


# Email Source CRUD Endpoints

@router.post("/api/settings/email-sources", response_model=AddEmailSourceResponse)
async def add_email_source(request: AddEmailSourceRequest):
    """Add a new email source with account pairs"""
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        config = config_storage.load_config(request.master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    source_dict = request.email_source.model_dump()
    config.setdefault('email_sources', []).append(source_dict)
    config_storage.save_config(config, request.master_password)

    return AddEmailSourceResponse(
        success=True,
        message="Email source added",
        source_id=source_dict['id']
    )


@router.delete("/api/settings/email-sources/{source_id}")
async def delete_email_source(source_id: str, request: DeleteEmailSourceRequest):
    """Delete an email source. Cannot delete the last one."""
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        config = config_storage.load_config(request.master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    sources = config.get('email_sources', [])

    # Find the source
    source_index = None
    for i, s in enumerate(sources):
        if s.get('id') == source_id:
            source_index = i
            break

    if source_index is None:
        raise HTTPException(status_code=404, detail="Email source not found")

    if len(sources) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last email source")

    sources.pop(source_index)
    config['email_sources'] = sources
    config_storage.save_config(config, request.master_password)

    return {"success": True, "message": "Email source deleted"}


@router.delete("/api/settings/email-sources/{source_id}/account-pairs/{pair_index}")
async def delete_account_pair(source_id: str, pair_index: int, request: DeleteEmailSourceRequest):
    """Delete an account pair from an email source. Cannot delete the last one."""
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        config = config_storage.load_config(request.master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    sources = config.get('email_sources', [])
    source = None
    for s in sources:
        if s.get('id') == source_id:
            source = s
            break

    if source is None:
        raise HTTPException(status_code=404, detail="Email source not found")

    pairs = source.get('account_pairs', [])

    if pair_index < 0 or pair_index >= len(pairs):
        raise HTTPException(status_code=404, detail="Account pair not found")

    if len(pairs) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last account pair")

    pairs.pop(pair_index)
    source['account_pairs'] = pairs
    config_storage.save_config(config, request.master_password)

    return {"success": True, "message": "Account pair deleted"}


# Year Progress Override Endpoint

@router.put("/api/settings/year-progress", response_model=YearProgressUpdateResponse)
async def update_year_progress(request: YearProgressUpdateRequest):
    """Update year progress override setting"""
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        config = config_storage.load_config(request.master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    config['year_progress_override'] = {
        'enabled': request.enabled,
        'months_above_nisab': request.months_above_nisab,
        'as_of_hijri_date': request.as_of_hijri_date,
    }
    config_storage.save_config(config, request.master_password)

    return YearProgressUpdateResponse(
        success=True,
        message="Year progress override updated"
    )


# Restart Setup Endpoint

@router.post("/api/settings/restart-setup", response_model=RestartSetupResponse)
async def restart_setup(request: RestartSetupRequest):
    """
    Get current decrypted config for pre-filling the setup wizard.
    Non-destructive - does not delete anything.
    """
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        config = config_storage.load_config(request.master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return RestartSetupResponse(success=True, config=config)


@router.post("/api/settings/delete")
async def delete_configuration(master_password: str):
    """Delete all configuration. Requires master password to confirm identity."""
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(status_code=404, detail="Configuration not found")

    try:
        config_storage.load_config(master_password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    config_storage.delete_config()
    return {"success": True, "message": "Configuration deleted"}


@router.put("/api/settings", response_model=SettingsUpdateResponse)
async def update_settings(request: SettingsUpdateRequest):
    """Update configuration settings"""
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration not found. Please complete setup first."
        )

    try:
        config = config_storage.load_config(request.master_password)

        if request.email_sources is not None:
            config['email_sources'] = [s.model_dump() for s in request.email_sources]

        if request.report_delivery is not None:
            config['report_delivery'] = request.report_delivery.model_dump()

        if request.year_progress_override is not None:
            config['year_progress_override'] = request.year_progress_override.model_dump()

        if request.additional_assets is not None:
            config['additional_assets'] = request.additional_assets

        if request.nisab_fallback_bam is not None:
            config['nisab_fallback_bam'] = request.nisab_fallback_bam

        config_storage.save_config(config, request.master_password)

        return SettingsUpdateResponse(
            success=True,
            message="Settings updated successfully"
        )

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating settings: {e}")


# History Endpoint

@router.get("/api/history", response_model=HistoryResponse)
async def get_history(master_password: str):
    """Get balance history"""
    # Load config to get encryption key
    config_storage = get_config_storage()

    if not config_storage.config_exists():
        raise HTTPException(
            status_code=404,
            detail="Configuration not found"
        )

    try:
        config = config_storage.load_config(master_password)
        encryption_key = config.get('encryption_key')

        if not encryption_key:
            raise HTTPException(status_code=500, detail="Encryption key not found in config")

        history_storage = HistoryStorage(encryption_key)
        entries = history_storage.load_history()

        # Convert to schema format
        history_entries = []
        for entry in entries:
            history_entries.append(BalanceHistoryEntry(
                hijri_date=entry.get('hijri_date', ''),
                gregorian_date=entry.get('gregorian_date', ''),
                balance_bam=entry.get('balance_bam', 0),
                balance_eur=entry.get('balance_eur', 0),
                total_bam=entry.get('total_bam', 0),
                nisab_threshold=entry.get('nisab_threshold', 0),
                above_nisab=entry.get('above_nisab', False),
                consecutive_months=entry.get('consecutive_months', 0)
            ))

        return HistoryResponse(
            entries=history_entries,
            total_count=len(history_entries)
        )

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading history: {e}")


# Nisab Endpoint

@router.get("/api/nisab", response_model=NisabResponse)
async def get_nisab():
    """Get current nisab threshold"""
    # For now, return fallback value
    # In full implementation, this would fetch from zekat.ba
    return NisabResponse(
        nisab_bam=24624.0,
        source="fallback",
        fetched_at=datetime.now().isoformat()
    )


# Analysis Endpoints

def _friendly_error_message(e: Exception) -> str:
    """Convert raw exceptions into user-friendly error messages."""
    msg = str(e).lower()

    # IMAP authentication errors
    if 'authenticationfailed' in msg or 'invalid credentials' in msg:
        return ("Email login failed: Invalid credentials. "
                "Make sure you're using a Gmail App Password (not your regular password). "
                "Go to Google Account > Security > 2-Step Verification > App passwords to generate one.")
    if 'login' in msg and ('fail' in msg or 'denied' in msg):
        return ("Email login failed. Check your email address and app password. "
                "Gmail requires an App Password when 2-Step Verification is enabled.")

    # Connection / network errors
    if 'getaddrinfo' in msg or 'nodename' in msg or 'name or service not known' in msg:
        return ("Cannot resolve IMAP server address. Check that the IMAP server name is correct "
                "(e.g. imap.gmail.com).")
    if 'connection refused' in msg:
        return ("Connection refused by email server. Check the IMAP server and port settings.")
    if 'timed out' in msg or 'timeout' in msg:
        return ("Connection to email server timed out. Check your internet connection and server settings.")
    if 'ssl' in msg:
        return f"SSL/TLS error connecting to email server: {e}"

    # Config errors
    if 'bam_account' in msg and 'eur_account' in msg:
        return "Bank account numbers not configured. Check your email source account pairs in Settings."
    if 'encryption' in msg or 'encryption_key' in msg:
        return "Encryption key is missing or invalid. Re-run setup or check Settings."

    # HTTP errors from get_adapter_from_config
    if hasattr(e, 'status_code'):
        if e.status_code == 401:
            return "Invalid master password."
        if e.status_code == 404:
            return "Configuration not found. Please complete setup first."

    return f"Analysis failed: {e}"


async def run_analysis_task(master_password: str):
    """
    Background task to run zakat analysis.
    Updates global analysis_progress state.
    Runs the blocking analysis in a thread to avoid blocking the event loop.
    """
    global analysis_progress

    try:
        analysis_progress["status"] = "running"
        analysis_progress["message"] = "Initializing analysis..."
        analysis_progress["progress"] = 10

        # Load adapter
        adapter = get_adapter_from_config(master_password)

        analysis_progress["message"] = "Connecting to email and retrieving statements..."
        analysis_progress["progress"] = 30

        # Run blocking analysis in thread executor so SSE stream can still send updates
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, adapter.run_analysis)

        analysis_progress["message"] = "Analysis complete"
        analysis_progress["progress"] = 100
        analysis_progress["status"] = "completed"
        analysis_progress["result"] = result
        _save_analysis_result(result)

        # Append a history entry so the History page has data
        try:
            config_storage = get_config_storage()
            config = config_storage.load_config(master_password)
            encryption_key = config.get('encryption_key')
            if encryption_key:
                history_storage = HistoryStorage(encryption_key)
                history_entry = {
                    'hijri_date': result.get('hijri_date', ''),
                    'gregorian_date': result.get('gregorian_date', datetime.now().strftime('%d.%m.%Y')),
                    'balance_bam': result.get('bank_balance', 0),
                    'balance_eur': 0,
                    'total_bam': result.get('total_assets', 0),
                    'nisab_threshold': result.get('nisab_threshold', 0),
                    'above_nisab': result.get('above_nisab', False),
                    'consecutive_months': result.get('consecutive_months_above_nisab', 0),
                    'timestamp': datetime.now().isoformat(),
                }
                # Extract EUR balance from sources if available
                for src in result.get('sources', []):
                    history_entry['balance_eur'] += src.get('eur_balance', 0)
                # Deduplicate by gregorian_date
                existing = history_storage.load_history()
                existing = [e for e in existing if e.get('gregorian_date') != history_entry['gregorian_date']]
                existing.append(history_entry)
                history_storage.save_history(existing[-24:])  # Keep last 24 entries
        except Exception as e:
            logger.warning(f"Could not save history entry: {e}")

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        analysis_progress["status"] = "error"
        analysis_progress["message"] = _friendly_error_message(e)
        analysis_progress["progress"] = 0
        analysis_progress["result"] = None


@router.post("/api/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(request: AnalyzeRequest):
    """
    Trigger zakat analysis in background.
    Use GET /api/analyze/progress to monitor progress via SSE.
    """
    global analysis_progress

    # Check if analysis already running
    if analysis_progress["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Analysis already in progress"
        )

    # Reset progress
    analysis_progress = {
        "status": "idle",
        "message": "",
        "progress": 0,
        "result": None
    }

    # Start task immediately (not after response) so SSE can track it
    asyncio.create_task(run_analysis_task(request.master_password))

    return AnalyzeResponse(
        success=True,
        message="Analysis started",
        task_id="analysis-1"  # In production, use unique IDs
    )


@router.get("/api/analyze/result")
async def get_last_analysis_result():
    """Get the last completed analysis result (if any).

    Returns the in-memory result first; falls back to the persisted file
    so the dashboard retains data across app restarts.
    """
    if analysis_progress["status"] == "completed" and analysis_progress["result"]:
        return {"success": True, "data": analysis_progress["result"]}

    # Fall back to persisted result from a previous session
    persisted = _load_analysis_result()
    if persisted:
        return {"success": True, "data": persisted}

    return {"success": False, "message": "No analysis result available"}


@router.get("/api/analyze/progress")
async def analysis_progress_stream():
    """
    Server-Sent Events stream for analysis progress.
    Streams progress updates until analysis completes or errors.
    """
    async def event_generator():
        """Generate SSE events"""
        last_status = None
        last_progress = -1

        while True:
            current_status = analysis_progress["status"]
            current_progress = analysis_progress["progress"]

            # Send update if status or progress changed
            if current_status != last_status or current_progress != last_progress:
                event_data = {
                    "event": current_status,
                    "message": analysis_progress["message"],
                    "progress": current_progress
                }

                # Include result if completed
                if current_status == "completed" and analysis_progress["result"]:
                    event_data["data"] = analysis_progress["result"]

                yield f"data: {json.dumps(event_data)}\n\n"

                last_status = current_status
                last_progress = current_progress

                # Stop streaming if completed or error
                if current_status in ["completed", "error"]:
                    break

            # Wait before checking again
            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


# Mark Paid Endpoint

@router.post("/api/mark-paid", response_model=MarkPaidResponse)
async def mark_zakat_paid(request: MarkPaidRequest):
    """Record zakat payment and reset cycle"""
    try:
        adapter = get_adapter_from_config(request.master_password)

        # Record payment
        success = adapter.record_zakat_payment(request.amount, request.hijri_date)

        if success:
            return MarkPaidResponse(
                success=True,
                message="Zakat payment recorded and cycle reset"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to record payment"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error recording payment: {e}"
        )
