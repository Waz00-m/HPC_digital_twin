"""Producer-only PDF builder. Requires reportlab; the boss's Mac does not run this."""
from html import escape
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/SmartBin-MacBook-Guide.pdf"
font_folder = Path("C:/Windows/Fonts")
if (font_folder / "arial.ttf").exists():
    for name, file in (("Guide", "arial.ttf"), ("Guide-Bold", "arialbd.ttf"), ("Guide-Code", "consola.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(font_folder / file)))
    normal, bold, mono = "Guide", "Guide-Bold", "Guide-Code"
else:
    normal, bold, mono = "Helvetica", "Helvetica-Bold", "Courier"
NAVY, TEAL, MUTED = colors.HexColor("#173244"), colors.HexColor("#14576A"), colors.HexColor("#425466")
styles = {
    "title": ParagraphStyle("title", fontName=bold, fontSize=25, leading=30, textColor=NAVY, spaceAfter=14),
    "h2": ParagraphStyle("h2", fontName=bold, fontSize=14, leading=18, textColor=NAVY, spaceBefore=14, spaceAfter=7, keepWithNext=True),
    "body": ParagraphStyle("body", fontName=normal, fontSize=10.5, leading=15, textColor=NAVY, spaceAfter=8),
    "small": ParagraphStyle("small", fontName=normal, fontSize=9, leading=12.5, textColor=MUTED, spaceAfter=7),
    "code": ParagraphStyle("code", fontName=mono, fontSize=9, leading=13, textColor=NAVY, backColor=colors.HexColor("#F0F4F6"), borderPadding=10, spaceBefore=6, spaceAfter=14),
    "cell": ParagraphStyle("cell", fontName=normal, fontSize=9, leading=12.5, textColor=NAVY),
}
story = []
def text(value, style="body"):
    story.append(Paragraph(escape(value).replace("\n", "<br/>"), styles[style]))
def title(value):
    story.append(Paragraph(escape(value).replace("\n", "<br/>"), styles["title"]))
def heading(value):
    story.append(Paragraph(escape(value), styles["h2"]))
def code(value):
    story.append(Preformatted(value, styles["code"]))
def step(number, value):
    text(str(number) + ". " + value)
def table(rows, widths):
    cells = [[Paragraph(escape(str(cell)), styles["cell"]) for cell in row] for row in rows]
    item = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    item.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#E8EFF3")),
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8), ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8), ("LINEBELOW", (0,0), (-1,0), .6, colors.HexColor("#B4C5CE")),
        ("LINEBELOW", (0,1), (-1,-1), .3, colors.HexColor("#D7E1E6"))]))
    story.extend([item, Spacer(1, 9)])
def page():
    story.append(PageBreak())

title("SmartBin digital twin\nMacBook setup guide")
text("Clean-machine setup and everyday operation • 25 November 2026", "small")
text("Use the supplied SmartBin-Mac-Demo.zip. The package contains the current nine-bin demo, its history pipeline, the model adapter placeholder and the Mac launchers.")
heading("Before starting")
table([("You need", "Details"), ("Mac", "Apple Silicon or Intel; a Docker Desktop-supported macOS release"),
       ("Resources", "8 GB physical RAM minimum; 16 GB recommended. Keep at least 20 GB disk space free."),
       ("Access", "Internet and your Mac administrator password. Leave Terminal open during installation.")], [110, 385])
text("Docker is the only host dependency. Node.js, Python, Ditto and MQTT run in containers. No separate Git, Homebrew, PowerShell or Protégé installation is needed.")
text("Existing Docker is reused, including normal, user-folder and Spotlight-registered custom installs. A stopped Desktop is opened; a running engine needs no install. Apple Silicon or Intel is detected automatically.", "small")
heading("First installation")
step(1, "Unzip SmartBin-Mac-Demo.zip. Move the extracted SmartBinDemo folder into your Home folder (Finder > Go > Home).")
step(2, "Open Terminal with Command+Space, type Terminal, and press Return. Run:")
code('cd "$HOME/SmartBinDemo"\nbash macos/setup.sh')
step(3, "If Docker is missing, its official installer requests your administrator password. Terminal shows no password characters while you type.")
step(4, "Finish Docker Desktop's first-run screens, terms and macOS permission prompts. The script waits for the engine and resumes automatically.")
step(5, "If requested, set Docker Desktop > Settings > Resources to at least 2 CPUs and 4 GB memory (6 GB preferred), Apply & Restart, and rerun the command.")
step(6, "Wait for ‘Setup complete’. The dashboard and spoofer open. On later days use Start-Mac.command.")
text("The script does not accept Docker's terms or dismiss system prompts for you. Large downloads and first service startup can take time. If setup stops, fix the displayed issue and run it again; committed data is preserved.", "small")

page(); title("Start, stop and find the tools")
table([("Launcher", "What it does"), ("Install-Mac.command", "Reuses installed components. Downloads/builds only missing or changed components; initializes OWL/MQTT when needed."),
       ("Start-Mac.command", "Starts the installed demo, preserving saved state. Restores spoofer controls from current Ditto readings."),
       ("Stop-Mac.command", "Stops this demo's containers while keeping databases, history and drafts."),
       ("Status-Mac.command", "Shows container and pipeline status without changing bin values.")], [145,350])
text("If Finder does not execute a downloaded command file, run its shell equivalent from Terminal in SmartBinDemo. Do not disable macOS security protections.")
code('bash macos/start.sh\nbash macos/stop.sh\nbash macos/status.sh')
heading("Browser addresses")
table([("Tool", "Address"), ("Warehouse dashboard", "http://127.0.0.1:4321/"), ("Separate spoofer", "http://127.0.0.1:4318/"),
       ("History metrics (JSON)", "http://127.0.0.1:4322/api/metrics"), ("Stored model-run results", "http://127.0.0.1:4322/api/model-runs"),
       ("Ditto Explorer", "http://127.0.0.1:8090/ui/")], [165,330])
heading("Ditto Explorer sign-in")
text("Choose the local environment. Sample main credentials: ditto / ditto. Optional DevOps credentials: devops / foobar. These are development defaults. Host-facing ports are bound to Mac loopback.")
text("The dashboard, spoofer and Python/history backend are separate services. Closing a browser tab does not stop them. Use Stop-Mac.command when finished.")
text("Repeat setup preserves readings and databases, reuses cached images and skips unchanged runtime builds. OWL/MQTT provisioning is skipped when its inputs are unchanged and the live check succeeds. Other Docker projects are left alone.", "small")

page(); title("Show the nine-bin demo")
heading("Change one real-time reading")
step(1, "Open the spoofer at http://127.0.0.1:4318/. Setup connects its broker; use Connect if it shows disconnected.")
step(2, "Choose Warehouse B and bin-002. Its demo capacity is 50 kg.")
step(3, "Move the slider to 30 kg. Press Send reading. Moving the slider alone only previews a value.")
step(4, "Open the dashboard. After its normal refresh, bin-002 should show 30 kg and 60% of rated weight. Select the bin to inspect its model, source and timestamps.")
step(5, "The history service stores the new Ditto revision. View /api/latest?include_thing=true on port 4322 to inspect the stored Thing.")
heading("What setup populates")
text("The first installation imports three warehouses and nine bins. Missing initial readings are seeded as three bins at 40%, three at 85% and three at 110%, giving normal, alert and overload examples. Existing readings are retained on repeat setup.")
text("These are illustrative load values. Percentage means rated weight, not occupied volume. Physical bins are not needed for this demonstration.")
heading("Explore the Scenario lab")
step(1, "Open Scenario lab in the dashboard. Expand Bin purposes & demand and review each bin's Collection or Inventory purpose, rate, alert and service time.")
step(2, "Choose duration, travel time and a delayed start. Expand the demand-burst and uncertainty settings if needed.")
step(3, "Press Compare strategies. Read the next job, its safety margin and the effect of starting late.")
step(4, "Use Inspect strategy to switch the schedule and per-bin outcomes between fixed route, threshold first and least time remaining.")
text("One shared team is occupied by travel and service while all bins continue changing. The three strategies use the same workload. Collection overflow and unmet inventory demand are reported separately.")
text("Simulation never publishes MQTT or changes live Things. Rates, travel, service and synthetic trials are demo assumptions. The handling rule is a heuristic; the boss's actual model is not connected yet.", "small")

page(); title("Thing history and Python")
text("Data path: spoofer → MQTT → Ditto Thing → indexed history database → Python adapter → stored result.")
text("The collector receives post-Ditto change notifications and retrieves complete Thing snapshots. It retains original JSON, warehouse/capacity context, revisions and timestamps. It does not subscribe to the raw MQTT stream.")
heading("Run the pipeline check")
text("Open Terminal in SmartBinDemo and run:")
code('bash macos/python.sh run-model')
text("Expected fields: model_name = pipeline-check; status = completed; prediction = false. The stored result proves retrieval and Python execution. It is not the boss's actual model.")
heading("Read and export")
code('bash macos/python.sh latest --include-thing\n\nbash macos/python.sh export --thing-id smartbin:bin-002 \\\n  --format csv --output /exports/bin-002.csv')
text("The CSV appears in SmartBinDemo/exports on the Mac. Observation time, Ditto modification time and reading time are separate fields. Missing/invalid data is flagged; regular sampling or interpolation is not fabricated.")
heading("Optional retrieval benchmark")
code('bash macos/python.sh benchmark --bins 100 --revisions 1000 \\\n  --directory /exports/benchmarks')
text("This creates a separate synthetic 100,000-version dataset and reports median/p95 query times on this Mac. The test does not pollute live history. Timings include warm query retrieval and Python row preparation, excluding network and inference.")
heading("Connect the supplied model later")
text("The pending file is history/models/boss_adapter.py. To implement it, obtain the model artifact/code, framework and version, feature names/order, units, time window, preprocessing and output format. Required libraries must be added to the container image when the real model is integrated.")
text("Every model run records exact input snapshot IDs, a hash, model identity, status and output. Failed runs are retained. Model results do not write to live Things. Collection gaps are recorded; an offline period cannot be assumed to contain complete history.", "small")

page(); title("If something stops")
heading("Docker is not ready")
text("Finish any first-run screens and wait for the engine. If setup times out, rerun Install-Mac.command. Existing Docker is not reinstalled. An incomplete installation or missing Compose produces a repair message.")
heading("Memory or CPU message")
text("In Docker Desktop > Settings > Resources, allocate at least 2 CPUs and 4 GB memory; 6 GB is preferred when physical RAM permits. Apply & Restart, then retry. On an 8 GB Mac, close other heavy apps and do not allocate all RAM to Docker.")
heading("Port already allocated")
text("Another app or another copy may use 8090, 1884, 4318, 4321 or 4322. Stop that known app through its own controls, then retry. The installer does not terminate unrelated processes.")
heading("Missing values or disconnected history")
text("Use Status-Mac.command. Check http://127.0.0.1:8090/health. On a clean installation use Install-Mac.command so OWL and missing readings are initialized. Java services may need several minutes on first startup.")
code('bash macos/logs.sh history\nbash macos/logs.sh gateway\nbash macos/logs.sh mqtt')
heading("Downloads or macOS compatibility")
text("Check internet access and retry. Native Apple Silicon and Intel image variants are pinned. Docker Desktop must support the installed macOS version; its installer enforces compatibility. Use the vendor's supported macOS policy rather than an old version assumption.")
heading("After editing app source or OWL")
text("Rerun Install-Mac.command. Only affected runtimes rebuild; changed or missing provisioning is reapplied. Readings, policy references, history and drafts are preserved. Guide-only edits do not rebuild apps.")
heading("Remote context or another demo folder")
text("Use this Mac's local Docker engine and the original SmartBinDemo folder. Setup refuses a remote endpoint or containers owned by another copy, preserving their data and context. Custom-app instructions are in the full guide.")
text("For the full copyable instructions, see docs/MACBOOK-GUIDE.md in the package. For application internals and the model contract, see history/README.md.", "small")

page(); title("Saved data and handoff notes")
table([("Data", "Location"), ("Ditto Things / policies", "Docker volume smartbin-mac_mongo-data"),
       ("MongoDB configuration", "Docker volume smartbin-mac_mongo-config"), ("MQTT sessions", "Docker volume smartbin-mac_mqtt-data"),
       ("Thing history / Python results", "history/.data/things.sqlite3 inside SmartBinDemo"), ("Scenario drafts", "dashboard/.data/scenarios.json"),
       ("Exports", "SmartBinDemo/exports"), ("Setup report / generated stack", ".runtime/mac/setup-report.json and compose.json")], [165,330])
text("Dot-prefixed folders are hidden in Finder; Command+Shift+Period toggles visibility. Stop-Mac.command keeps data. Removing Docker volumes or deleting project data is a separate reset, not an everyday stop. The source ZIP alone is not a backup of runtime databases.")
heading("What was checked")
text("The OWL mapping matches the Windows importer and was checked against all 12 Things without changes. Shell syntax, generated Compose and Linux container runtimes were verified. Pinned images support both chip architectures. Mocked tests cover Docker reuse, missing components, cached builds, remote contexts and folder ownership.")
text("The native macOS installer and its GUI approval steps require the target Mac and cannot be fully exercised from this Windows workstation. Follow the first-run checks before using the demo in front of visitors.")
heading("Official references")
for label,url in (("Docker Desktop installation and macOS support", "https://docs.docker.com/desktop/setup/install/mac-install/"),
                  ("Ditto resources and deployment", "https://eclipse.dev/ditto/installation-running.html"),
                  ("Thing change notifications", "https://eclipse.dev/ditto/httpapi-sse.html"),
                  ("Project repository", "https://github.com/Waz00-m/HPC_digital_twin")):
    text(label, "small")
    story.append(Paragraph('<link href="'+url+'" color="#14576A">'+escape(url)+'</link>',styles['small']))
text("Use the supplied Mac ZIP as this handoff's source snapshot. Any other checkout must contain macos/, history/ and the Mac launchers for this guide to apply.", "small")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CCD8DF")); canvas.setLineWidth(.5)
    canvas.line(18*mm,17*mm,A4[0]-18*mm,17*mm)
    canvas.setFont(normal,8); canvas.setFillColor(MUTED)
    canvas.drawString(18*mm,12*mm,"SmartBin digital twin • MacBook handoff • 25 November 2026")
    canvas.drawRightString(A4[0]-18*mm,12*mm,str(doc.page))
    canvas.restoreState()

OUTPUT.parent.mkdir(exist_ok=True)
document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                             topMargin=17*mm, bottomMargin=23*mm, title="SmartBin digital twin — MacBook setup guide", author="SmartBin project")
document.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUTPUT)
