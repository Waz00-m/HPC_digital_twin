"""Producer tool using the bundled python-docx runtime; not run on the boss's Mac."""
from pathlib import Path
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/SmartBin-MacBook-Guide.docx"
IMAGES = ROOT / "docs/images/mac-guide"
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin, sec.bottom_margin = Inches(.68), Inches(.68)
sec.left_margin, sec.right_margin = Inches(.8), Inches(.8)
sec.header_distance, sec.footer_distance = Inches(.27), Inches(.3)
WIDTH = 6.9

def font(style, size, bold=False, color="202020"):
    style.font.name = "Arial"
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor.from_string(color)
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:ascii"), "Arial")
    style.element.rPr.rFonts.set(qn("w:hAnsi"), "Arial")

font(doc.styles["Normal"], 11)
normal = doc.styles["Normal"].paragraph_format
normal.line_spacing = 1.12
normal.space_after = Pt(7)
font(doc.styles["Title"], 25, True, "000000")
doc.styles["Title"].paragraph_format.space_after = Pt(12)
font(doc.styles["Heading 1"], 18, True, "000000")
doc.styles["Heading 1"].paragraph_format.space_before = Pt(0)
doc.styles["Heading 1"].paragraph_format.space_after = Pt(12)
font(doc.styles["Heading 2"], 12.5, True, "173244")
doc.styles["Heading 2"].paragraph_format.space_before = Pt(10)
doc.styles["Heading 2"].paragraph_format.space_after = Pt(7)
font(doc.styles["Caption"], 9.5, False, "444444")
doc.styles["Caption"].paragraph_format.space_before = Pt(5)
doc.styles["Caption"].paragraph_format.space_after = Pt(8)
for name in ("Title", "Heading 1", "Heading 2"):
    ppr = doc.styles[name].element.find(qn("w:pPr"))
    if ppr is not None:
        for item in list(ppr):
            if item.tag in (qn("w:pBdr"), qn("w:shd")):
                ppr.remove(item)

header = sec.header.paragraphs[0]
header.add_run("SmartBin digital twin    Mac operation guide").font.size = Pt(8)
header.runs[0].font.color.rgb = RGBColor.from_string("555555")
footer = sec.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
footer.add_run("Updated 26 November 2026    |    ").font.size = Pt(8)
field = OxmlElement("w:fldSimple"); field.set(qn("w:instr"), "PAGE")
footer._p.append(field)
doc.core_properties.title = "SmartBin Mac setup and Python data retrieval"
doc.core_properties.subject = "Operating the nine-bin demo and fetching timed database samples"
doc.core_properties.author = "SmartBin project"
doc.core_properties.keywords = "Mac SmartBin Ditto Python database samples operation guide"

def p(text, *, bold=False, size=None, keep=False):
    para = doc.add_paragraph()
    para.paragraph_format.keep_with_next = keep
    run = para.add_run(text); run.bold = bold
    if size:
        run.font.size = Pt(size)
    return para

def h(text):
    return doc.add_heading(text, 2)

def page(title):
    heading = doc.add_heading(title, 1)
    heading.paragraph_format.page_break_before = True

def step(number, text):
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Inches(.23)
    para.paragraph_format.first_line_indent = Inches(-.23)
    para.add_run(str(number) + ". ").bold = True
    para.add_run(text)
    return para

def code(text):
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Inches(.12)
    para.paragraph_format.space_before = Pt(2)
    para.paragraph_format.space_after = Pt(9)
    para.paragraph_format.line_spacing = 1.05
    para.paragraph_format.keep_together = True
    run = para.add_run(text)
    run.font.name = "Consolas"; run.font.size = Pt(10)
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:ascii"), "Consolas")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Consolas")
    return para

def table(headers, rows, widths):
    item = doc.add_table(rows=1, cols=len(headers))
    item.alignment = WD_TABLE_ALIGNMENT.CENTER
    item.autofit = False
    for column, width in zip(item.columns, widths):
        column.width = Inches(width)
    for index, value in enumerate(headers):
        item.rows[0].cells[index].text = value
    for values in rows:
        cells = item.add_row().cells
        for index, value in enumerate(values):
            cells[index].text = str(value)
    for row_index, row in enumerate(item.rows):
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if row_index == 0:
            trpr.append(OxmlElement("w:tblHeader"))
        for index, cell in enumerate(row.cells):
            cell.width = Inches(widths[index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = cell._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for side in ("top", "left", "bottom", "right"):
                element = OxmlElement("w:" + side)
                for name, value in (("val", "single"), ("sz", "4"), ("color", "D9D9D9")):
                    element.set(qn("w:" + name), value)
                borders.append(element)
            tcpr.append(borders)
            margins = OxmlElement("w:tcMar")
            for side in ("top", "left", "bottom", "right"):
                element = OxmlElement("w:" + side)
                element.set(qn("w:w"), "90"); element.set(qn("w:type"), "dxa")
                margins.append(element)
            tcpr.append(margins)
            fill = "E8EFF4" if row_index == 0 else "F6F8FA" if row_index % 2 else "FFFFFF"
            shade = OxmlElement("w:shd"); shade.set(qn("w:fill"), fill); tcpr.append(shade)
            for para in cell.paragraphs:
                para.paragraph_format.space_after = Pt(1)
                para.paragraph_format.line_spacing = 1.08
                for run in para.runs:
                    run.font.size = Pt(10.5); run.bold = row_index == 0
    p("").paragraph_format.space_after = Pt(1)
    return item

def figure(name, caption, alt, width=WIDTH):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_after = Pt(0)
    para.paragraph_format.keep_with_next = True
    image = para.add_run().add_picture(str(IMAGES / name), width=Inches(width))
    image._inline.docPr.set("descr", alt)
    doc.add_paragraph(caption, style="Caption")

def link(label, url):
    para = doc.add_paragraph()
    rel = para.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    item = OxmlElement("w:hyperlink"); item.set(qn("r:id"), rel)
    run = OxmlElement("w:r"); prop = OxmlElement("w:rPr")
    color = OxmlElement("w:color"); color.set(qn("w:val"), "14576A"); prop.append(color)
    run.append(prop); text = OxmlElement("w:t"); text.text = label; run.append(text)
    item.append(run); para._p.append(item)

doc.add_paragraph("SmartBin Mac setup and Python data retrieval", style="Title")
p("Operator guide    Updated 26 November 2026", size=10)
p("Use this guide to run three warehouses and nine virtual SmartBins on a Mac, save their Ditto values in a database, and retrieve those values for Python models. Physical bins are not required for this demo. The supplied model can be connected later without changing how data is fetched.")
p("The ready path is to install once, start the services, send or hold a weight, then export the stored rows. The history service saves timed observations every 30 seconds, including unchanged weights.")
h("Choose the right section")
table(("What you need", "Where to go"), (
    ("First setup on this Mac", "Page 2"),
    ("Start the installed demo and check it", "Page 3"),
    ("Send a reading and see the result", "Pages 4 and 5"),
    ("Check repeated values and export data", "Pages 6 and 7"),
    ("Understand fields or connect a model", "Pages 8 to 11"),
    ("Fix a problem or update an older copy", "Pages 12 and 13"),
), (4.9, 2.0))
h("Have these ready")
table(("Item", "Requirement for this demo"), (
    ("Mac", "Apple Silicon or Intel, with a macOS version supported by Docker Desktop"),
    ("Memory and storage", "At least 8 GB physical RAM and 20 GB free space for first setup; 16 GB RAM is recommended"),
    ("Access", "Internet connection and a Mac administrator password if installation is needed"),
    ("Code package", "The updated SmartBin-Mac-Demo.zip supplied with this guide"),
), (1.65, 5.25))
p("Docker supplies the app runtimes. Separate host Python and Node installations are unnecessary. Setup detects the chip type and reuses an existing compatible Docker installation.")
p("About the pictures  The five figures are actual browser screenshots from the running development demo, captured on 26 November 2026. The same browser pages run on Mac. Native Mac installer and Terminal screens are described with copyable commands; they have not been pictured as if tested on a Mac.", size=9.5)

page("1 Install the demo once")
step(1, "Save SmartBin-Mac-Demo.zip on the Mac. For a fresh installation, double click it in Finder to extract the SmartBinDemo folder.")
step(2, "In Finder choose Go then Home. Move the extracted SmartBinDemo folder there. Keep this name and location so the commands below work.")
step(3, "Open Terminal using Command and Space, type Terminal, and press Return. Paste these commands, pressing Return after each line.")
code('cd "$HOME/SmartBinDemo"\nbash macos/setup.sh')
step(4, "Leave Terminal open. Complete any Docker Desktop first run screens and macOS permission prompts. If the official installer asks for your administrator password, type it and press Return; Terminal normally shows no password characters.")
step(5, "If setup requests more Docker resources, open Docker Desktop Settings then Resources. Allocate at least 2 CPU cores and 4 GB memory, or 6 GB when the Mac has enough RAM. Choose Apply and Restart, then rerun the setup command.")
step(6, "Wait for Setup complete. The separate warehouse dashboard and spoofer should open. First image downloads and Ditto startup can take several minutes.")
h("What is reused automatically")
table(("What setup finds", "What happens"), (
    ("Docker is running", "It is reused; installation is skipped"),
    ("Docker Desktop is installed but stopped", "The existing app is opened and setup waits for its engine"),
    ("Docker is missing", "The official installer for the detected chip is downloaded"),
    ("Cached images and unchanged app code", "Downloads and builds are skipped where possible"),
    ("Existing saved demo", "Readings, history and drafts are preserved; missing setup is repaired"),
), (2.8, 4.1))
p("If SmartBinDemo already exists, keep using that same folder. Follow the update procedure on page 13 instead of replacing it with a second extracted copy. Setup refuses a remote Docker engine or a stack owned by another folder.")
p("Setup prepares Ditto, MQTT, the three warehouses and nine bins from the OWL model, the spoofer, dashboard, history database and Python pipeline. It publishes initial readings only where they are missing.")

page("2 Start and check the installed demo")
step(1, "On later days, open Start-Mac.command in SmartBinDemo. If Finder does not run the file, open Terminal and use the commands below.")
code('cd "$HOME/SmartBinDemo"\nbash macos/start.sh')
step(2, "Open the browser addresses in the table. The history service starts with the rest of the stack and begins collecting timed samples immediately.")
table(("Tool", "Browser address"), (
    ("Warehouse dashboard", "http://127.0.0.1:4321/"),
    ("Separate spoofer", "http://127.0.0.1:4318/"),
    ("Pipeline status and counts", "http://127.0.0.1:4322/api/metrics"),
    ("History health", "http://127.0.0.1:4322/health"),
    ("Ditto Explorer when needed", "http://127.0.0.1:8090/ui/"),
), (2.45, 4.45))
step(3, "In metrics, check sample_seconds is 30, last_sample_error is null, and last_sampled_at advances after about 30 seconds. Refresh the browser page to see new counts. connected reports the separate change stream connection.")
figure("history-metrics.jpg", "Figure 1  Actual collector status and database counts. This crop shows the collector and counts area; values increase while the service runs.", "History metrics showing a connected collector, a 30 second sample interval, no sampling error, and separate counts for samples and snapshots", width=6.6)
p("latest_things normally counts 12 because the database includes nine bins and three warehouses. The Python fetcher returns SmartBin rows. The samples counter includes the stored warehouse observations too. Some browsers offer a Pretty print checkbox to make JSON easier to read.", size=10)

page("3 Send a bin reading")
step(1, "Open http://127.0.0.1:4318/ and wait for Ready to send. If disconnected, use Reconnect local broker and wait for the connection.")
step(2, "Choose Warehouse B and bin-002. Confirm its capacity is 50 kg. Select a single bin so the action applies to that bin.")
step(3, "Move the slider to 20 kg. Use Exact values and slider options if you need precise entry. Moving the slider only prepares a draft.")
figure("spoofer-controls.jpg", "Figure 2  Actual spoofer controls with Warehouse B and bin-002 selected. Send reading publishes the prepared value once.", "Spoofer showing bin-002 with a 50 kilogram capacity, a 20 kilogram preview, the slider and Send reading button")
step(4, "Press Send reading. A broker acknowledgement confirms MQTT receipt. Use the warehouse dashboard to confirm that Ditto also received the reading.")
step(5, "Open http://127.0.0.1:4321/. bin-002 should show 20 kg and 40 percent of rated weight after the normal refresh. A 30 kg reading would show 60 percent.")
p("Sending the same weight again creates another receipt timestamp when Ditto processes it. Independently, the database timer continues to save observations even if you send nothing else. To demonstrate a constant value, keep the bin in Hold mode and leave automatic publishing paused.")
h("Keep the two apps separate")
p("The spoofer is the mock sensor that sends MQTT. The warehouse dashboard reads the current Ditto Things. The history backend stores those Things and timed observations for Python. Changing a slider without sending does not update the live twin.")

page("4 See the values in the dashboard")
p("The overview groups three bins under each warehouse. Select a bin card to inspect its capacity, alert threshold, receipt timestamp, MQTT source and Thing ID. Use the warehouse filters to focus the view.")
figure("warehouse-overview.jpg", "Figure 3  Actual nine-bin warehouse overview. This demo has normal, attention and overload examples. The screen refreshes current Ditto values; it is separate from the stored history.", "Warehouse dashboard containing three warehouse groups with three bins each, current weights, percentages and status badges", width=6.25)
p("Percentages describe rated weight. For example, 20 kg divided by a 50 kg capacity is 40 percent. These values do not measure occupied volume. A last receipt time describes the reading timestamp and is not proof that a physical bin is online.", size=10)

page("5 Verify that unchanged weights are saved")
step(1, "Keep the services running with the selected bin held at one weight. Wait at least 65 seconds so several timer polls can complete.")
step(2, "Open http://127.0.0.1:4322/api/samples?thing_id=smartbin%3Abin-002. Use Pretty print if available. Look for different sample_id and sampled_at values with the same weight_kg.")
figure("timed-samples.jpg", "Figure 4  Two actual bin-002 records from a bounded query. Both hold 20 kg and revision 20. Their sample IDs and observation times differ.", "Two database sample records retaining 20 kilograms, a shared original receipt timestamp, and distinct observation times and sample IDs", width=5.55)
p("In this captured example the observations are from 26 November and the original reading_at is from 25 November. The timer has observed an older reading again; it has not created a fresh sensor measurement. After you send a new reading, reading_at changes to that new receipt time.", size=10)

page("6 Fetch the data as JSON or CSV")
p("Run these commands in Mac Terminal after starting the installed demo. The Python fetcher opens the existing database read only. It requires no knowledge of which model will process the rows later.")
code('cd "$HOME/SmartBinDemo"')
h("Export all timed SmartBin samples as JSON")
code('bash macos/python.sh fetch \\\n  --output /exports/all-bins.json')
p("JSON contains a rows list, the selected series, filter details, column names, source identity and a hash of the rows. Each row also includes the full original Ditto Thing under thing.")
h("Export the same series as CSV")
code('bash macos/python.sh fetch --format csv \\\n  --output /exports/all-bins.csv')
p("CSV can be opened with Numbers or Excel. The thing column contains a JSON object serialized into that cell. Add --no-thing if the model needs only the flattened columns.")
h("Export one bin")
code('bash macos/python.sh fetch --thing-id smartbin:bin-002 \\\n  --output /exports/bin-002.json')
h("Find the files on the Mac")
code('open "$HOME/SmartBinDemo/exports"')
p("The container path /exports maps to the exports folder in SmartBinDemo on the Mac. Export success reports exported_rows and output. A later export to the same filename replaces that export file; it does not change database records. Exports are static files, so rerun the command to include later rows.")
p("The default limit is 50,000 rows. If it is exceeded, the command fails with a narrowing instruction rather than silently omitting rows. Use a time window or warehouse filter from page 9. Invalid or awaiting readings remain visible unless you explicitly select --valid-only.")

page("7 Understand the returned values")
figure("bin-details.jpg", "Figure 5  Actual bin detail panel. The capacity and threshold provide context for the raw received weight. All original Thing fields remain available in a JSON export.", "Bin-002 detail panel showing 20 kilograms, a 50 kilogram capacity, a 42.5 kilogram alert threshold, receipt timestamp, MQTT source and identity", width=6.5)
table(("Field", "Meaning"), (
    ("sample_id and sampled_at", "One timed database observation and its capture time"),
    ("reading_at", "Receipt time of the original load reading; it stays unchanged if no new reading arrived"),
    ("observed_at", "First database capture of that complete Thing revision"),
    ("snapshot_id and revision", "The stored complete Thing version referenced by the timed row"),
    ("thing_id bin_id warehouse_id", "Which bin and warehouse this row belongs to"),
    ("weight_kg capacity_kg weight_percent", "Received kilograms, modeled capacity and calculated weight utilization"),
    ("quality status source", "Input validity, weight state and reading origin; valid does not guarantee freshness"),
    ("thing", "Full original Thing JSON, including attributes and features beyond the flattened columns"),
), (2.5, 4.4))
p("Timestamps ending in Z are UTC. Browser labels may use the Mac local timezone. Timed rows preserve the original reading time so the model can apply its own freshness policy. Alert fields use the capacity and threshold stored with that historical Thing version.", size=10)

page("8 Choose the series and filters")
p("The fetcher keeps timed observations separate from revision history. It never removes a row just because its weight equals the previous row.")
table(("Series", "What you get", "Time filter uses"), (
    ("samples", "Default timed observations, including unchanged values", "sampled_at"),
    ("revisions", "Complete Thing versions already captured, including history from before timed sampling was enabled", "observed_at"),
    ("latest", "Only the latest stored state for each bin", "No time window"),
), (1.1, 4.15, 1.65))
h("One warehouse and a time window")
p("Replace the example dates with a range containing data on this Mac. Include Z for UTC, or an explicit offset such as +05:30. Bounds are inclusive.")
code('bash macos/python.sh fetch --warehouse-id warehouse-b \\\n  --since 2026-11-26T00:00:00Z \\\n  --until 2026-11-27T00:00:00Z \\\n  --format csv --output /exports/warehouse-b.csv')
h("Retrieve earlier revision history")
code('bash macos/python.sh fetch --series revisions \\\n  --thing-id smartbin:bin-002 \\\n  --output /exports/bin-002-revisions.json')
h("Retrieve only the latest bin values")
code('bash macos/python.sh fetch --series latest --no-thing \\\n  --output /exports/latest-bins.json')
p("Use --valid-only when the model explicitly needs structurally valid rows only. A valid row can still contain an old reading; compare reading_at with the model's freshness requirement. An empty result can mean the selected dates or IDs have no matching stored data.")
p("Timed sampling begins when the updated history service starts. Existing revisions remain available, but old gaps are not converted into invented timed samples. Slow or failed Ditto requests can leave gaps; inspect the collector log when interpreting a model window.")

page("9 Run the Python pipeline check")
p("The working pipeline check proves that Python can query the database and store a result. It is a test adapter; your boss's actual model has not yet been supplied.")
code('cd "$HOME/SmartBinDemo"\nbash macos/python.sh run-model \\\n  --input-series samples --limit 50000')
h("Check the returned result")
table(("Field", "Expected value"), (
    ("model_name", "pipeline-check"),
    ("status", "completed"),
    ("output.prediction", "false"),
    ("manifest.input_series", "samples"),
    ("output.input_rows", "A positive number when valid timed bin rows are available"),
    ("run_id", "The identifier of this saved execution"),
), (2.5, 4.4))
p("The model runner defaults to a window covering the last 24 hours. This command selects timed samples explicitly and allows up to 50,000 input rows. It excludes invalid readings and non-bin records while retaining their IDs as exclusions in its manifest.")
h("View saved runs")
p("Open http://127.0.0.1:4322/api/model-runs in the browser. Copy a run_id from the result if you want to inspect or replay that exact input selection.")
code('bash macos/python.sh get-run YOUR_RUN_ID --include-inputs')
p("Replace YOUR_RUN_ID with the actual identifier. The stored manifest records the model identity, chosen series, exact sample and snapshot IDs, input hash, time window and completion status. Repeating a weight does not collapse those sample IDs.")
h("What the current dashboard shows")
p("The warehouse dashboard shows current Things and its existing Scenario lab. Saved model outputs are currently accessible through the history API. The dedicated results dashboard will be designed after the actual model output format is known.")

page("10 Hand the rows to the supplied models")
p("The stable input boundary is a list of dictionaries returned by fetch_data. The boss can turn that list into the DataFrame, array or tensor required by his model. Fetching does not assume a machine learning framework.")
h("Python integration example")
p("This example runs inside the history container, where the database is /data/things.sqlite3 and twin_history is already importable. For code running directly on the Mac, add SmartBinDemo/history to the import path and pass the host database path SmartBinDemo/history/.data/things.sqlite3.", size=10)
code('from twin_history.reader import fetch_data\n\ndata = fetch_data(\n    db_path="/data/things.sqlite3",\n    thing_id="smartbin:bin-002",\n    valid_only=True,\n)\nrows = data["rows"]\n# Pass rows to the actual model here.')
h("Use the prepared adapter when ready")
p("The integration file is history/models/boss_adapter.py. It currently raises a clear model not supplied error. Implement its run function only after receiving the actual model code or artifact and its input contract.")
p("Obtain the framework and version, feature names and order, units, desired time series, time window, preprocessing, freshness rules and output schema. Add any required libraries to the history container image, then rerun setup to rebuild it.")
p("After the adapter is implemented, the operator command is:")
code('bash macos/python.sh run-model --input-series samples \\\n  --adapter models/boss_adapter.py --limit 50000')
p("The adapter returns JSON-serializable results. The runner saves successful or failed executions in model_runs; results do not change live bins. The current test adapter and this placeholder should not be presented as the boss's real prediction model.")
h("Validation and references")
p("Timed sampling, repeated weights, read-only retrieval, exports, schema migration and exact model-input replay were checked with isolated tests and the live development demo. Mac Compose generation was checked. Native macOS installation and its permission screens have not been exercised on this Windows workstation.", size=9.5)
link("Docker Desktop official Mac installation and support", "https://docs.docker.com/desktop/setup/install/mac-install/")
link("Eclipse Ditto Thing change notifications", "https://eclipse.dev/ditto/httpapi-sse.html")

page("11 Troubleshoot a stopped or empty pipeline")
table(("What you see", "What to do"), (
    ("Docker is not ready", "Finish its first run screens. Start Docker Desktop, then rerun setup or start. Setup keeps an existing installation."),
    ("Memory or CPU request", "Adjust Docker Settings then Resources, Apply and Restart, and retry."),
    ("Port already allocated", "Check the app using 8090, 1884, 4318, 4321 or 4322. Stop that known app through its own controls; avoid terminating unrelated processes."),
    ("unknown command fetch", "This is older code. Apply the updated package in the same folder using page 13, then rerun setup."),
    ("Database does not exist or old schema", "Start or update the history service. The read-only fetcher deliberately does not create or migrate an empty database."),
    ("No rows returned", "Wait for two timer cycles. Check the bin or warehouse ID, date window, selected series and last_sample_error."),
    ("Query exceeds row limit", "Narrow the bin, warehouse or dates. Data has not been silently truncated."),
    ("Last sample time is not advancing", "Refresh metrics. Confirm Ditto health and inspect history logs. Failed polls create sample-gap notices instead of rows."),
    ("Same weight appears many times", "This is expected for samples. Use reading_at to distinguish repeated observations from newly received sensor readings."),
    ("Remote context or another folder owns stack", "Select the local Mac engine and use the original demo folder. Setup does not change remote contexts or replace another copy's containers."),
), (2.25, 4.65))
h("Commands for diagnosis")
code('cd "$HOME/SmartBinDemo"\nbash macos/status.sh\nbash macos/logs.sh history\nbash macos/logs.sh mqtt')
p("Read http://127.0.0.1:8090/health for Ditto health. The history collector notices are at http://127.0.0.1:4322/api/collector-log. Follow the displayed error before rerunning setup.")

page("12 Stop update and keep the saved data")
h("Stop the demo")
code('cd "$HOME/SmartBinDemo"\nbash macos/stop.sh')
p("This stops only the demo containers. Database records and scenario drafts remain. No timer samples are written while collection is stopped, and missed intervals are not backfilled. Restart with bash macos/start.sh.")
h("Update an existing copy in place")
p("Save the updated SmartBin-Mac-Demo.zip in Downloads. Keep the ZIP compressed for this procedure, save your open files, and run:")
code('cd "$HOME/SmartBinDemo"\nbash macos/stop.sh\nunzip -o "$HOME/Downloads/SmartBin-Mac-Demo.zip" -d "$HOME"\nbash macos/setup.sh')
p("This package is rooted at SmartBinDemo and excludes local databases and runtime state. Extraction overlays the supplied source files in the original Home folder; it does not remove the saved folders listed below. Do not replace the whole folder or start a duplicate copy. Use your actual original location if it differs from the standard Home location.")
h("Where the saved files live")
table(("Data", "Location"), (
    ("Thing history and model runs", "SmartBinDemo/history/.data/things.sqlite3"),
    ("Scenario drafts", "SmartBinDemo/dashboard/.data/scenarios.json"),
    ("Exported model inputs", "SmartBinDemo/exports"),
    ("Ditto Things and policies", "Docker volume smartbin-mac_mongo-data"),
    ("Generated stack and setup report", "SmartBinDemo/.runtime/mac"),
), (2.4, 4.5))
p("Dot folders are hidden in Finder; Command and Shift and Period toggles them. A source ZIP is not a database backup. Do not delete Docker volumes to stop the demo. For backups during collection, use SQLite's backup API or stop the service before copying its database files.", size=10)
h("Change the timer interval")
code('TWIN_SAMPLE_SECONDS=10 bash macos/setup.sh')
p("Valid intervals are 1 to 3,600 whole seconds. The Mac setup saves the chosen interval for later starts and setup reruns. Check sample_seconds in metrics after the service restarts.", size=10)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUTPUT)
print(OUTPUT)
