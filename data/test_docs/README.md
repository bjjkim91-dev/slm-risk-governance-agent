# Sample documents

Five example bundles so you can try the agent without preparing your own documents. Each set has the three inputs the upload page asks for.

| Set | Regulation (public-domain US federal text, printed from eCFR) | Controls | Processes |
|---|---|---|---|
| 1 | 31 CFR 1020.220, customer identification programs | `Control Inventory.xlsx` | `Process narratives.docx` |
| 2 | 31 CFR 1020.210, anti-money-laundering programs | `Control Inventory.xlsx` | `Process narratives.docx` |
| 3 | 31 CFR 1020.320, suspicious transaction reports | `Control Inventory.xlsx` | `Process narratives.docx` |
| 4 | 31 CFR 1010.311, currency transaction reports | `Control Inventory.xlsx` | `Process narratives.docx` |
| 5 | 31 CFR 1010.230, beneficial ownership | `Control Inventory.xlsx` | `Process narratives.docx` |

Control inventories and process narratives are synthetic. Nothing here comes from a real organisation. Sets 1, 4 and 5 were rebuilt from the training records (`training_reference/rebuild_sample_sets.py`), so their regulation PDFs are plain text rather than eCFR prints.

The expected outputs for every set, used as training labels and evaluation truth, are under `training_reference/Set N/`.

**How to use them**

1. Start the app and open the upload page.
2. Upload the three files from **one** set: the PDF as the regulation, the spreadsheet as controls, the narrative as processes.
3. Run Phase 1, Phase 2 and Phase 3 in order.
