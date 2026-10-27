"""Counter software for a small community pharmacy.

Stock is kept per batch and sold first-expiring first, prescriptions are filled within
their refill limits after a dosage check, controlled medicines need a pharmacist's
approval, and every sale produces a receipt.
"""

__all__ = ["controlled", "dispensing", "inventory", "models", "prescriptions", "receipts"]
