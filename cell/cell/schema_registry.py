from __future__ import annotations


class ResultSchemaRegistry:
    """Pre-defined result schemas for common task types."""

    @staticmethod
    def verification() -> dict:
        return {
            "type": "object",
            "properties": {
                "verified": {"type": "boolean"},
                "confidence": {"type": "number"},
                "findings": {"type": "array"},
                "discrepancies": {"type": "array"},
            },
            "required": ["verified", "confidence"],
        }

    @staticmethod
    def analysis() -> dict:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "key_findings": {"type": "array"},
                "data_points": {"type": "object"},
                "recommendations": {"type": "array"},
            },
            "required": ["summary", "key_findings"],
        }

    @staticmethod
    def generation() -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "format": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["content"],
        }

    @staticmethod
    def review() -> dict:
        return {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "issues": {"type": "array"},
                "passed": {"type": "boolean"},
                "comments": {"type": "array"},
            },
            "required": ["issues", "passed"],
        }

    @staticmethod
    def extraction() -> dict:
        return {
            "type": "object",
            "properties": {
                "extracted_data": {"type": "object"},
                "extraction_coverage": {"type": "number"},
                "unprocessed_sections": {"type": "array"},
            },
            "required": ["extracted_data"],
        }

    @staticmethod
    def custom(schema: dict) -> dict:
        return schema

