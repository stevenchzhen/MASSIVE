from cellforge import CellForge


def main() -> None:
    cell = CellForge.from_env()
    result = cell.run(
        "Extract the invoice number, invoice date, due date, vendor name, and total amount from the attached invoice note.",
        documents=["examples/document_extraction/invoice_note.txt"],
        result_schema={
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string"},
                "invoice_number": {"type": "string"},
                "invoice_date": {"type": "string"},
                "due_date": {"type": "string"},
                "total_amount_usd": {"type": "number"},
            },
            "required": ["vendor_name", "invoice_number", "invoice_date", "due_date", "total_amount_usd"],
        },
        result_schema_id="invoice_extraction",
        artifacts_dir=".artifacts/document-extraction",
    )
    print(result.result)


if __name__ == "__main__":
    main()
