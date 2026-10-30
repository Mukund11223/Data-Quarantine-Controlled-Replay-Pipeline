from datetime import datetime, timezone

SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "JPY"}


# ============================================================
# Stage 1: Schema Validation — Required Fields Present
# ============================================================
def validate_required_fields(record: dict) -> tuple[list[str], list[str]]:
    """
    Check that all required fields exist and are non-empty.
    Returns (error_codes, error_messages).
    """
    error_codes = []
    error_messages = []

    order_id = str(record.get("order_id", "")).strip()
    customer_id = str(record.get("customer_id", "")).strip()
    order_date_raw = str(record.get("order_date", "")).strip()
    amount_raw = record.get("total_amount", "")

    if not order_id:
        error_codes.append("ERR_MISSING_ORDER_ID")
        error_messages.append("Order ID is missing or empty.")

    if not customer_id:
        error_codes.append("ERR_MISSING_CUSTOMER_ID")
        error_messages.append("Customer ID is missing or empty.")

    if not order_date_raw:
        error_codes.append("ERR_MISSING_DATE")
        error_messages.append("Order date is missing or empty.")

    if amount_raw == "" or amount_raw is None:
        error_codes.append("ERR_MISSING_AMOUNT")
        error_messages.append("Total amount is missing or empty.")

    return error_codes, error_messages


# ============================================================
# Stage 2: Type & Format Validation
# ============================================================
def parse_amount(amount_raw) -> tuple[float | None, list[str], list[str]]:
    """
    Parse total_amount to float.
    Returns (amount_or_None, error_codes, error_messages).
    """
    error_codes = []
    error_messages = []
    try:
        amount = float(amount_raw)
        return amount, error_codes, error_messages
    except (ValueError, TypeError):
        error_codes.append("ERR_MALFORMED_AMOUNT")
        error_messages.append(f"Total amount '{amount_raw}' is not a valid number.")
        return None, error_codes, error_messages


def parse_order_date(order_date_raw: str) -> tuple[datetime | None, list[str], list[str]]:
    """
    Parse order_date to timezone-naive UTC datetime.
    Also checks for future timestamps.
    Returns (datetime_or_None, error_codes, error_messages).
    """
    error_codes = []
    error_messages = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        order_date = datetime.fromisoformat(order_date_raw.replace("Z", "+00:00"))
        if order_date.tzinfo is not None:
            order_date = order_date.replace(tzinfo=None)
        if order_date > now:
            error_codes.append("ERR_FUTURE_TIMESTAMP")
            error_messages.append(f"Order date '{order_date_raw}' is in the future.")
        return order_date, error_codes, error_messages
    except (ValueError, TypeError):
        error_codes.append("ERR_MALFORMED_DATE")
        error_messages.append(f"Order date '{order_date_raw}' is not a valid ISO-8601 timestamp.")
        return None, error_codes, error_messages


def check_batch_duplicate(order_id: str, seen_batch_ids: set) -> tuple[list[str], list[str]]:
    """
    Check for duplicate order_id within the current batch.
    Returns (error_codes, error_messages).
    """
    error_codes = []
    error_messages = []
    if order_id in seen_batch_ids:
        error_codes.append("ERR_DUPLICATE_KEY")
        error_messages.append(f"Duplicate order_id '{order_id}' found within the batch.")
    return error_codes, error_messages


# ============================================================
# Stage 3: Domain Business Rules
# ============================================================
def validate_business_rules(amount: float, currency: str) -> tuple[list[str], list[str]]:
    """
    Validate domain rules: amount > 0, currency supported.
    Returns (error_codes, error_messages).
    """
    error_codes = []
    error_messages = []

    if amount <= 0:
        error_codes.append("ERR_NEGATIVE_AMOUNT")
        error_messages.append(f"Total amount '{amount}' must be strictly greater than 0.")

    if currency not in SUPPORTED_CURRENCIES:
        error_codes.append("ERR_UNSUPPORTED_CURRENCY")
        error_messages.append(f"Currency '{currency}' is not supported. Allowed: {sorted(list(SUPPORTED_CURRENCIES))}.")

    return error_codes, error_messages


# ============================================================
# Stage 4: Referential & State Integrity
# ============================================================
def validate_customer_reference(
    customer_id: str,
    valid_customers: set,
    active_customers: set
) -> tuple[list[str], list[str]]:
    """
    Validate customer exists and is active.
    Returns (error_codes, error_messages).
    """
    error_codes = []
    error_messages = []

    if customer_id not in valid_customers:
        error_codes.append("ERR_INVALID_CUSTOMER")
        error_messages.append(f"Customer ID '{customer_id}' does not exist in reference dimension.")
    elif customer_id not in active_customers:
        error_codes.append("ERR_INACTIVE_CUSTOMER")
        error_messages.append(f"Customer '{customer_id}' account is suspended or closed.")

    return error_codes, error_messages


# ============================================================
# Main Orchestrator — Public API (unchanged signature)
# ============================================================
def validate_record(
    record: dict,
    valid_customers: set,
    active_customers: set,
    seen_batch_ids: set
) -> tuple[bool, list[str], list[str], str]:
    """
    Validates a single record against all rules.
    Returns (is_valid, error_codes, error_messages, failed_stage).
    """
    all_error_codes = []
    all_error_messages = []
    failed_stage = "NONE"

    # Extract & normalize fields early
    order_id = str(record.get("order_id", "")).strip()
    customer_id = str(record.get("customer_id", "")).strip()
    order_date_raw = str(record.get("order_date", "")).strip()
    amount_raw = record.get("total_amount", "")
    currency = str(record.get("currency", "")).strip().upper()

    # Stage 1: Required Fields
    codes, msgs = validate_required_fields(record)
    all_error_codes.extend(codes)
    all_error_messages.extend(msgs)
    if codes:
        return False, all_error_codes, all_error_messages, "SCHEMA_VALIDATION"

    # Stage 2: Type/Format + Batch Duplicate
    codes, msgs = check_batch_duplicate(order_id, seen_batch_ids)
    all_error_codes.extend(codes)
    all_error_messages.extend(msgs)
    if codes:
        return False, all_error_codes, all_error_messages, "UNIQUENESS_CHECK"

    amount, codes, msgs = parse_amount(amount_raw)
    all_error_codes.extend(codes)
    all_error_messages.extend(msgs)
    if amount is None:
        return False, all_error_codes, all_error_messages, "SCHEMA_VALIDATION"

    order_date, codes, msgs = parse_order_date(order_date_raw)
    all_error_codes.extend(codes)
    all_error_messages.extend(msgs)
    if order_date is None:
        return False, all_error_codes, all_error_messages, "SCHEMA_VALIDATION"

    # Stage 3: Business Rules
    codes, msgs = validate_business_rules(amount, currency)
    all_error_codes.extend(codes)
    all_error_messages.extend(msgs)

    # Stage 4: Referential Integrity
    codes, msgs = validate_customer_reference(customer_id, valid_customers, active_customers)
    all_error_codes.extend(codes)
    all_error_messages.extend(msgs)

    if all_error_codes:
        return False, all_error_codes, all_error_messages, "BUSINESS_RULE"

    return True, [], [], "NONE"