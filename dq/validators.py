"""Lightweight data quality validators for ingested items."""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import ValidationError

from market_pulse.models.dto import IngestItem

logger = logging.getLogger(__name__)

# Common valid language codes (ISO 639-1 plus some common variations)
VALID_LANGUAGES = {
    "en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko", 
    "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi",
    "en-us", "en-gb", "pt-br", "zh-cn", "zh-tw"
}

# Minimum and maximum reasonable text lengths
MIN_TEXT_LENGTH = 10
MAX_TEXT_LENGTH = 50000  # Much longer than DTO constraint for initial validation

# URL validation patterns
SUSPICIOUS_URL_PATTERNS = [
    r"localhost",
    r"127\.0\.0\.1",
    r"\.test$",
    r"\.local$",
    r"example\.com",
]


class ValidationResult:
    """Result of data quality validation."""
    
    def __init__(self, is_valid: bool, errors: Optional[list[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def add_error(self, error: str) -> None:
        """Add validation error."""
        self.is_valid = False
        self.errors.append(error)


def validate_url(url: str) -> ValidationResult:
    """Validate URL format and content.
    
    Args:
        url: URL string to validate
        
    Returns:
        ValidationResult with any errors found
    """
    result = ValidationResult(True)
    
    try:
        parsed = urlparse(url)
        
        # Check for valid scheme
        if parsed.scheme not in ("http", "https"):
            result.add_error(f"Invalid URL scheme: {parsed.scheme}")
        
        # Check for valid netloc
        if not parsed.netloc:
            result.add_error("URL missing domain")
        
        # Check for suspicious patterns
        for pattern in SUSPICIOUS_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                result.add_error(f"Suspicious URL pattern: {pattern}")
        
        # Check URL length
        if len(url) > 2000:
            result.add_error(f"URL too long: {len(url)} chars")
            
    except Exception as e:
        result.add_error(f"URL parsing error: {str(e)}")
    
    return result


def validate_language(lang: str) -> ValidationResult:
    """Validate language code.
    
    Args:
        lang: Language code to validate
        
    Returns:
        ValidationResult with any errors found
    """
    result = ValidationResult(True)
    
    if not lang:
        result.add_error("Language code is empty")
        return result
    
    # Normalize to lowercase
    lang_normalized = lang.lower().strip()
    
    if lang_normalized not in VALID_LANGUAGES:
        result.add_error(f"Unknown language code: {lang}")
    
    return result


def validate_text_content(text: str, field_name: str = "text") -> ValidationResult:
    """Validate text content length and basic quality.
    
    Args:
        text: Text content to validate
        field_name: Name of the field for error messages
        
    Returns:
        ValidationResult with any errors found
    """
    result = ValidationResult(True)
    
    if not text or not text.strip():
        result.add_error(f"{field_name} is empty or whitespace-only")
        return result
    
    text_len = len(text.strip())
    
    if text_len < MIN_TEXT_LENGTH:
        result.add_error(f"{field_name} too short: {text_len} chars (min {MIN_TEXT_LENGTH})")
    
    if text_len > MAX_TEXT_LENGTH:
        result.add_error(f"{field_name} too long: {text_len} chars (max {MAX_TEXT_LENGTH})")
    
    # Check for excessive repetition (simple heuristic)
    words = text.split()
    if len(words) > 10:
        unique_words = set(words)
        repetition_ratio = len(words) / len(unique_words)
        if repetition_ratio > 5.0:
            result.add_error(f"{field_name} has excessive word repetition (ratio: {repetition_ratio:.2f})")
    
    return result


def validate_ingest_item(item: IngestItem) -> ValidationResult:
    """Comprehensive validation of an IngestItem.
    
    Args:
        item: IngestItem to validate
        
    Returns:
        ValidationResult with any errors found
    """
    result = ValidationResult(True)
    
    try:
        # Pydantic validation will handle basic type/constraint checks
        item.model_validate(item.model_dump())
    except ValidationError as e:
        for error in e.errors():
            result.add_error(f"Pydantic validation: {error['msg']} at {error['loc']}")
    
    # URL validation
    url_result = validate_url(str(item.url))
    if not url_result.is_valid:
        result.errors.extend([f"URL: {err}" for err in url_result.errors])
        result.is_valid = False
    
    # Language validation
    if item.lang:
        lang_result = validate_language(item.lang)
        if not lang_result.is_valid:
            result.errors.extend([f"Language: {err}" for err in lang_result.errors])
            result.is_valid = False
    
    # Text content validation
    if item.title:
        title_result = validate_text_content(item.title, "title")
        if not title_result.is_valid:
            result.errors.extend(title_result.errors)
            result.is_valid = False
    
    if item.text:
        text_result = validate_text_content(item.text, "text")
        if not text_result.is_valid:
            result.errors.extend(text_result.errors)
            result.is_valid = False
    
    # Timestamp validation
    if item.published_at > item.retrieved_at:
        result.add_error("published_at cannot be after retrieved_at")
    
    return result


def canonicalize_url(url: str) -> str:
    """Canonicalize URL for deduplication.
    
    Removes common tracking parameters and normalizes format.
    
    Args:
        url: Original URL
        
    Returns:
        Canonicalized URL string
    """
    try:
        parsed = urlparse(url)
        
        # Remove common tracking parameters
        if parsed.query:
            # Split query parameters
            params = []
            for param in parsed.query.split("&"):
                if "=" in param:
                    key, _ = param.split("=", 1)
                    # Skip common tracking parameters
                    if key.lower() not in {
                        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
                        "fbclid", "gclid", "msclkid", "ref", "referrer", "_ga", "_gl"
                    }:
                        params.append(param)
                else:
                    params.append(param)
            
            query = "&".join(params) if params else ""
        else:
            query = ""
        
        # Normalize fragment (usually remove it)
        fragment = ""
        
        # Reconstruct URL
        from urllib.parse import urlunparse
        canonical = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") if parsed.path != "/" else "/",
            parsed.params,
            query,
            fragment
        ))
        
        return canonical
        
    except Exception as e:
        logger.warning(f"Failed to canonicalize URL {url}: {e}")
        return url  # Return original if canonicalization fails


def compute_title_simhash64(title: str) -> str:
    """Compute 64-bit simhash of title for near-duplicate detection.
    
    This is a simple implementation. In production, you might want to use
    a proper simhash library with better text preprocessing.
    
    Args:
        title: Article title
        
    Returns:
        Hex string of 64-bit hash
    """
    import hashlib
    
    if not title:
        return "0000000000000000"
    
    # Simple preprocessing: lowercase, remove punctuation, split words
    import string
    cleaned = title.lower().translate(str.maketrans("", "", string.punctuation))
    words = cleaned.split()
    
    if not words:
        return "0000000000000000"
    
    # Very simple simhash approximation using regular hash
    # In production, implement proper simhash algorithm
    word_hashes = [hashlib.md5(word.encode()).hexdigest() for word in words[:10]]  # Limit to first 10 words
    combined = "".join(word_hashes)
    
    # Take first 64 bits (16 hex chars) of SHA256
    final_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    return final_hash

