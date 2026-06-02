import csv
import math

from ij import IJ, Prefs
from ij import ImagePlus
from ij.measure import ResultsTable
from ij.io import DirectoryChooser, FileInfo
from ij.gui import Overlay, Roi, TextRoi
from java.io import File, FileWriter, BufferedReader, InputStreamReader
from java.awt import BorderLayout, Color, Font, GridBagConstraints, GridBagLayout, Insets
from java.awt.event import ActionListener
from java.lang import ProcessBuilder, Thread, System as JavaSystem
from java.text import SimpleDateFormat
from java.util import Date
from ij.plugin.frame import RoiManager
from ij.process import ShortProcessor
from javax.swing import ImageIcon, JButton, JCheckBox, JComboBox, JFrame, JLabel, JPanel, JScrollPane, JTabbedPane, JTable, JTextArea, JTextField
from javax.swing.table import DefaultTableModel
from org.json import JSONObject
from fiji.util.gui import GenericDialogPlus

DEFAULT_BUBMASK_PROJECT = "C:\\Users\\arman\\tor_mere\\bubmask-fiji"
PROJECT_PREF_KEY = "bubmask.project.path"


def clean_path(path):
    if path is None:
        return ""
    value = str(path).strip().strip('"')
    while value.endswith("\\") or value.endswith("/"):
        value = value[:-1]
    return value


def join_path(root, *parts):
    file_obj = File(root)
    for part in parts:
        file_obj = File(file_obj, part)
    return file_obj.getPath()


def project_has_worker(project_path):
    if project_path is None or str(project_path).strip() == "":
        return False
    return File(join_path(project_path, "src", "main", "python", "bubmask_worker.py")).exists()


def discover_bubmask_project():
    candidates = [
        JavaSystem.getenv("BUBMASK_FIJI_PROJECT"),
        Prefs.get(PROJECT_PREF_KEY, ""),
        DEFAULT_BUBMASK_PROJECT,
    ]
    for candidate in candidates:
        project_path = clean_path(candidate)
        if project_has_worker(project_path):
            Prefs.set(PROJECT_PREF_KEY, project_path)
            Prefs.savePreferences()
            return project_path

    IJ.showMessage(
        "BubMask setup",
        "Select the downloaded bubmask-fiji project folder.\n\n"
        "It should contain src/main/python/bubmask_worker.py and the models folder."
    )
    chooser = DirectoryChooser("Select downloaded bubmask-fiji project folder")
    selected = clean_path(chooser.getDirectory())
    if project_has_worker(selected):
        Prefs.set(PROJECT_PREF_KEY, selected)
        Prefs.savePreferences()
        return selected

    IJ.showMessage(
        "BubMask setup",
        "BubMask-Fiji project folder was not configured.\n\n"
        "Set BUBMASK_FIJI_PROJECT or rerun BubMask and select the folder that contains "
        "src/main/python/bubmask_worker.py."
    )
    return selected


def discover_python(project_path):
    windows_python = join_path(project_path, ".venv-bubmask", "Scripts", "python.exe")
    unix_python = join_path(project_path, ".venv-bubmask", "bin", "python")
    if File(windows_python).exists():
        return windows_python
    if File(unix_python).exists():
        return unix_python
    return windows_python


BUBMASK_PROJECT = discover_bubmask_project()
BUBMASK_PYTHON = discover_python(BUBMASK_PROJECT)
BUBMASK_WORKER = join_path(BUBMASK_PROJECT, "src", "main", "python", "bubmask_worker.py")
BUBMASK_MODEL = join_path(BUBMASK_PROJECT, "models", "bubmask-maskrcnn-v1")
BUBMASK_MODEL_UNSW_ROUND2 = join_path(BUBMASK_PROJECT, "models", "bubmask-maskrcnn-unsw-round2-v1")
BUBMASK_MODEL_UNSW_ROUND3 = join_path(BUBMASK_PROJECT, "models", "bubmask-maskrcnn-unsw-round3-v1")
BUBMASK_RESULTS_DIR = join_path(BUBMASK_PROJECT, "results")
BUBMASK_MODEL_CHOICES = [
    "Original BubMask Mask R-CNN",
    "UNSW Round 2 fine-tune (provisional)",
    "UNSW Round 3 fine-tune (provisional)",
]
BUBMASK_MODEL_PATHS = {
    BUBMASK_MODEL_CHOICES[0]: BUBMASK_MODEL,
    BUBMASK_MODEL_CHOICES[1]: BUBMASK_MODEL_UNSW_ROUND2,
    BUBMASK_MODEL_CHOICES[2]: BUBMASK_MODEL_UNSW_ROUND3,
}

SUMMARY_ROWS = []
OUTPUT_ROWS = []
MEASUREMENT_ROWS = []
LOG_LINES = []


def json_escape(value):
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def display_value(value):
    if value is None:
        return ""
    return str(value)


def log_message(message):
    LOG_LINES.append(display_value(message))


def write_text(path, text):
    writer = FileWriter(path)
    try:
        writer.write(text)
    finally:
        writer.close()


def list_files_recursive(file_obj):
    files = []
    if file_obj is None or not file_obj.exists():
        return files
    if file_obj.isFile():
        files.append(file_obj)
        return files
    children = file_obj.listFiles()
    if children is not None:
        for child in children:
            files.extend(list_files_recursive(child))
    return files


def delete_tree(file_obj):
    if file_obj is None or not file_obj.exists():
        return True
    ok = True
    if file_obj.isDirectory():
        children = file_obj.listFiles()
        if children is not None:
            for child in children:
                ok = delete_tree(child) and ok
    if not file_obj.delete():
        ok = False
        log_message("Could not delete: " + file_obj.getAbsolutePath())
    return ok


def remove_empty_dirs(file_obj, keep_root):
    if file_obj is None or not file_obj.exists() or file_obj.isFile():
        return
    children = file_obj.listFiles()
    if children is not None:
        for child in children:
            remove_empty_dirs(child, keep_root)
    children = file_obj.listFiles()
    if file_obj.getAbsolutePath() != keep_root.getAbsolutePath() and (children is None or len(children) == 0):
        file_obj.delete()


def canonical_path(path):
    if path is None or str(path).strip() == "":
        return ""
    return str(File(path).getAbsolutePath()).lower()


def read_process_stream(stream):
    reader = BufferedReader(InputStreamReader(stream))
    lines = []
    line = reader.readLine()
    while line is not None:
        lines.append(line)
        line = reader.readLine()
    return "\n".join(lines)


def original_image_path(imp):
    info = imp.getOriginalFileInfo()
    if info is not None and info.directory is not None and info.fileName is not None:
        candidate = File(info.directory, info.fileName)
        if candidate.isFile():
            return candidate.getAbsolutePath()
    return None


def ensure_image_file(imp, run_dir):
    path = original_image_path(imp)
    if path is not None:
        return path
    export_path = File(run_dir, "active_image_export.tif").getAbsolutePath()
    IJ.saveAs(imp, "Tiff", export_path)
    return export_path


def safe_name(value):
    text = str(value)
    safe = []
    for ch in text:
        if ch.isalnum() or ch in ["-", "_", "."]:
            safe.append(ch)
        else:
            safe.append("_")
    return "".join(safe)


def create_run_dir(imp):
    stamp = SimpleDateFormat("yyyyMMdd_HHmmss").format(Date())
    folder = "bubmask_run_" + stamp + "_" + safe_name(imp.getTitle())
    run_dir = File(BUBMASK_RESULTS_DIR, folder)
    run_dir.mkdirs()
    return run_dir


def run_worker(request_path, response_path):
    pb = ProcessBuilder([
        BUBMASK_PYTHON,
        BUBMASK_WORKER,
        "--input",
        request_path,
        "--output",
        response_path,
    ])
    pb.directory(File(BUBMASK_PROJECT))
    process = pb.start()
    stdout = read_process_stream(process.getInputStream())
    stderr = read_process_stream(process.getErrorStream())
    exit_code = process.waitFor()
    return exit_code, stdout, stderr


def status_color(status, fallback):
    return fallback


def draw_detection_overlay(imp, data, inference_mode, overlay_mode):
    masks = data.getJSONArray("masks")
    measurements = data.getJSONArray("measurements") if data.has("measurements") else None
    status_by_id = {}
    if measurements is not None:
        for j in range(measurements.length()):
            row = measurements.getJSONObject(j)
            status_by_id[row.optInt("bubble_id", j + 1)] = row.optString("measurement_status", "")
    overlay = Overlay()
    if overlay_mode == "masks_only":
        imp.setOverlay(overlay)
        imp.updateAndDraw()
        return 0, masks.length()

    if inference_mode == "bubmask_mask_rcnn":
        color = Color(0, 255, 0)
    elif inference_mode == "adaptive_threshold_baseline":
        color = Color(255, 255, 0)
    else:
        color = Color(0, 200, 255)

    limit = masks.length()
    if inference_mode == "adaptive_threshold_baseline" and limit > 250:
        limit = 250

    for i in range(limit):
        item = masks.getJSONObject(i)
        bubble_id = item.optInt("id", i + 1)
        bbox = item.getJSONArray("bbox")
        x = bbox.getDouble(0)
        y = bbox.getDouble(1)
        w = bbox.getDouble(2)
        h = bbox.getDouble(3)
        roi = Roi(x, y, w, h)
        draw_color = status_color(status_by_id.get(bubble_id, ""), color)
        roi.setStrokeColor(draw_color)
        roi.setStrokeWidth(2 if inference_mode == "bubmask_mask_rcnn" else 1)
        overlay.add(roi)

        if inference_mode == "bubmask_mask_rcnn":
            label = TextRoi(x, max(0, y - 10), str(bubble_id))
            label.setStrokeColor(draw_color)
            label.setFont(Font("SansSerif", Font.PLAIN, 10))
            overlay.add(label)

    imp.setOverlay(overlay)
    imp.updateAndDraw()
    return limit, masks.length()


def open_mask_overlay_image(outputs, overlay_mode):
    if overlay_mode == "boxes_only":
        return ""
    mask_overlay = outputs.optString("overlay_masks_png") if outputs is not None else ""
    if mask_overlay and File(mask_overlay).isFile():
        IJ.open(mask_overlay)
    else:
        mask_overlay = ""
    return mask_overlay


def open_processing_previews(outputs, preview_mode):
    opened = []
    if outputs is None or preview_mode == "none":
        return ""
    preview = outputs.optString("processing_preview_png")
    if preview and File(preview).isFile():
        IJ.open(preview)
        opened.append(preview)
    if preview_mode == "all_processing_images":
        for key in ["background_corrected_png", "preprocessed_png", "fov_mask_tif"]:
            path = outputs.optString(key)
            if path and File(path).isFile():
                IJ.open(path)
                opened.append(path)
    return "; ".join(opened)


def add_summary_row(rt, section, field, value):
    rt.incrementCounter()
    rt.addValue("section", section)
    rt.addValue("field", field)
    rt.addValue("value", "" if value is None else str(value))
    SUMMARY_ROWS.append([display_value(section), display_value(field), display_value(value)])


def add_output_row(rt, artifact, path):
    if path:
        rt.incrementCounter()
        rt.addValue("artifact", artifact)
        rt.addValue("path", path)
        OUTPUT_ROWS.append([display_value(artifact), display_value(path)])


def compact_measurement_table(measurements, unit):
    rt = ResultsTable()
    limit = measurements.length()
    if limit > 500:
        limit = 500
    for i in range(limit):
        row = measurements.getJSONObject(i)
        rt.incrementCounter()
        rt.addValue("id", row.optInt("bubble_id", i + 1))
        rt.addValue("status", "bubble")
        rt.addValue("histogram", "True")
        rt.addValue("score", row.optDouble("score"))
        rt.addValue("diameter", row.optDouble("equivalent_diameter_calibrated"))
        rt.addValue("unit", row.optString("diameter_unit", unit))
        rt.addValue("area_px", row.optDouble("area_px"))
        rt.addValue("x_px", row.optDouble("centroid_x_px"))
        rt.addValue("y_px", row.optDouble("centroid_y_px"))
        rt.addValue("reason", "")
        rt.addValue("flags", "")
        MEASUREMENT_ROWS.append([
            display_value(row.optInt("bubble_id", i + 1)),
            "bubble",
            "True",
            display_value(row.optDouble("score")),
            display_value(row.optDouble("equivalent_diameter_calibrated")),
            row.optString("diameter_unit", unit),
            display_value(row.optDouble("area_px")),
            display_value(row.optDouble("centroid_x_px")),
            display_value(row.optDouble("centroid_y_px")),
            "",
            "",
        ])
    return rt, limit, measurements.length()


def format_rows(columns, rows):
    all_rows = [columns] + rows
    widths = []
    for idx in range(len(columns)):
        width = len(display_value(columns[idx]))
        for row in rows:
            if idx < len(row):
                width = max(width, len(display_value(row[idx])))
        widths.append(min(width, 80))
    lines = []
    for row_index, row in enumerate(all_rows):
        parts = []
        for idx in range(len(columns)):
            text = display_value(row[idx] if idx < len(row) else "")
            if len(text) > widths[idx]:
                text = text[:max(0, widths[idx] - 3)] + "..."
            parts.append(text.ljust(widths[idx]))
        lines.append("  ".join(parts))
        if row_index == 0:
            lines.append("  ".join(["-" * width for width in widths]))
    return "\n".join(lines)


def text_tab(text):
    area = JTextArea(text)
    area.setEditable(False)
    area.setLineWrap(False)
    area.setFont(Font("Monospaced", Font.PLAIN, 12))
    return JScrollPane(area)


def bubble_display_rows():
    rows = []
    for row in MEASUREMENT_ROWS:
        rows.append([row[0], row[1], row[3], row[4], row[5], row[6], row[7], row[8]])
    return rows


def show_tabbed_results():
    frame = JFrame("BubMask Results")
    tabs = JTabbedPane()
    tabs.addTab("Run Summary", text_tab(format_rows(["Section", "Field", "Value"], SUMMARY_ROWS)))
    tabs.addTab(
        "Bubble Measurements",
        text_tab(format_rows(
            ["ID", "Status", "Score", "Diameter", "Unit", "Area px", "X px", "Y px"],
            bubble_display_rows(),
        )),
    )
    tabs.addTab("Output Files", text_tab(format_rows(["Artifact", "Path or status"], OUTPUT_ROWS)))
    tabs.addTab("Log", text_tab("\n".join(LOG_LINES)))
    frame.getContentPane().add(tabs, BorderLayout.CENTER)
    frame.setSize(1100, 720)
    frame.setLocationRelativeTo(None)
    frame.setVisible(True)


def add_artifact_choice(choices, label, path, default_keep):
    if path and File(path).isFile():
        choices.append([label + " (" + File(path).getName() + ")", File(path).getAbsolutePath(), default_keep])


def collect_artifact_choices(run_dir, request_path, response_path, stdout_path, stderr_path, outputs):
    choices = []
    manual_hist_csv = File(run_dir, "diameter_with_manual_histogram_all.csv").getAbsolutePath()
    manual_hist_png = File(run_dir, "diameter_with_manual_histogram_all.png").getAbsolutePath()
    manual_xlsx = File(run_dir, "bubble_measurements_with_manual.xlsx").getAbsolutePath()
    manual_overlay = File(run_dir, "overlay_with_manual_bubbles.png").getAbsolutePath()
    manual_labels = File(run_dir, "instance_labels_with_manual.tif").getAbsolutePath()
    histogram_csv = manual_hist_csv if File(manual_hist_csv).isFile() else ""
    histogram_png = manual_hist_png if File(manual_hist_png).isFile() else ""
    bubble_xlsx = manual_xlsx if File(manual_xlsx).isFile() else File(run_dir, "bubble_measurements.xlsx").getAbsolutePath()
    mask_overlay = manual_overlay if File(manual_overlay).isFile() else ""
    instance_labels = manual_labels if File(manual_labels).isFile() else ""
    box_overlay = ""
    audit_json = ""
    if outputs is not None:
        if not histogram_csv:
            histogram_csv = outputs.optString("diameter_histogram_all_csv")
        if not histogram_png:
            histogram_png = outputs.optString("diameter_histogram_all_png")
        if not mask_overlay:
            mask_overlay = outputs.optString("overlay_masks_png")
        if not instance_labels:
            instance_labels = outputs.optString("instance_labels_tif")
        box_overlay = outputs.optString("overlay_png")
        audit_json = outputs.optString("summary_json")
    add_artifact_choice(choices, "Histogram CSV", histogram_csv, True)
    add_artifact_choice(choices, "Histogram PNG", histogram_png, True)
    add_artifact_choice(choices, "Bubble list Excel", bubble_xlsx, True)
    add_artifact_choice(choices, "Mask overlay picture", mask_overlay, True)
    add_artifact_choice(choices, "Boxes overlay picture", box_overlay, True)
    add_artifact_choice(choices, "Instance-label mask TIFF", instance_labels, True)
    add_artifact_choice(choices, "Run audit JSON", audit_json, True)
    return choices


def prompt_result_retention(artifact_choices):
    modes = ["Save recommended output package", "Choose output files", "Do not save files"]
    dialog = GenericDialogPlus("BubMask Result Files")
    dialog.addMessage("Choose final outputs to keep. Other internal worker files will be deleted.")
    dialog.addChoice("Result file handling", modes, modes[0])
    dialog.addMessage("Recommended package: histogram CSV/PNG, Excel bubble list, overlay pictures, label mask, and audit JSON.")
    for item in artifact_choices:
        dialog.addCheckbox(item[0], item[2])
    dialog.showDialog()
    if dialog.wasCanceled():
        return modes[0], []
    mode = dialog.getNextChoice()
    selected_paths = []
    for item in artifact_choices:
        keep = dialog.getNextBoolean()
        if mode == modes[0] and item[2]:
            selected_paths.append(item[1])
        elif mode == modes[1] and keep:
            selected_paths.append(item[1])
    return mode, selected_paths


def prune_to_selected_files(run_dir, selected_paths):
    keep = {}
    for path in selected_paths:
        keep[canonical_path(path)] = True
    for file_obj in list_files_recursive(run_dir):
        if canonical_path(file_obj.getAbsolutePath()) not in keep:
            if not file_obj.delete():
                log_message("Could not delete unselected file: " + file_obj.getAbsolutePath())
    remove_empty_dirs(run_dir, run_dir)


def filter_output_rows_to_existing(retention_status):
    global OUTPUT_ROWS
    kept_rows = []
    for row in OUTPUT_ROWS:
        if len(row) > 1 and File(row[1]).exists():
            kept_rows.append(row)
    OUTPUT_ROWS = kept_rows
    OUTPUT_ROWS.append(["result retention", retention_status])


def apply_result_retention(run_dir, artifact_choices):
    mode, selected_paths = prompt_result_retention(artifact_choices)
    if mode == "Do not save files":
        delete_tree(run_dir)
        status = "Result files deleted completely."
    else:
        if len(selected_paths) == 0:
            delete_tree(run_dir)
        else:
            prune_to_selected_files(run_dir, selected_paths)
        remaining_files = list_files_recursive(run_dir)
        if len(remaining_files) == 0:
            delete_tree(run_dir)
            status = "No selected files remained; result folder deleted."
        elif File(run_dir.getAbsolutePath()).isDirectory():
            status = "Saved selected output package in " + run_dir.getAbsolutePath()
        else:
            status = "No selected files remained; result folder deleted."
    filter_output_rows_to_existing(status)
    return status


def collect_manual_rois(imp, mode):
    rois = []
    if mode == "current_active_roi":
        roi = imp.getRoi()
        if roi is not None:
            rois.append(roi.clone())
        else:
            log_message("Manual bubble mode selected, but the active image has no current ROI.")
    elif mode == "roi_manager_all":
        manager = RoiManager.getInstance()
        if manager is None or manager.getCount() == 0:
            log_message("Manual bubble mode selected, but ROI Manager has no ROIs.")
        else:
            roi_array = manager.getRoisAsArray()
            for roi in roi_array:
                rois.append(roi.clone())
    return rois


def csv_escape(value):
    text = display_value(value)
    if "," in text or "\n" in text or "\r" in text or '"' in text:
        text = '"' + text.replace('"', '""') + '"'
    return text


def write_csv_rows(path, fieldnames, rows):
    lines = [",".join([csv_escape(field) for field in fieldnames])]
    for row in rows:
        lines.append(",".join([csv_escape(row.get(field, "")) for field in fieldnames]))
    write_text(path, "\n".join(lines) + "\n")


def read_csv_rows(path):
    if path is None or path == "" or not File(path).isFile():
        return [], []
    handle = open(path, "r")
    try:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(row)
        return list(reader.fieldnames), rows
    finally:
        handle.close()


def equivalent_diameter_from_area(area, pixel_width, pixel_height):
    if area <= 0:
        return 0.0
    area_calibrated = area * pixel_width * pixel_height
    return 2.0 * math.sqrt(area_calibrated / math.pi)


def get_label_processor(outputs, width, height):
    label_path = outputs.optString("instance_labels_tif") if outputs is not None else ""
    if label_path and File(label_path).isFile():
        label_imp = IJ.openImage(label_path)
        if label_imp is not None:
            return label_imp.getProcessor().duplicate()
    return ShortProcessor(width, height)


def max_label_value(ip):
    max_value = 0
    for y in range(ip.getHeight()):
        for x in range(ip.getWidth()):
            value = int(ip.getPixel(x, y))
            if value > max_value:
                max_value = value
    return max_value


def measure_and_add_roi_to_label(label_ip, roi, bubble_id):
    width = label_ip.getWidth()
    height = label_ip.getHeight()
    temp = ShortProcessor(width, height)
    temp.setValue(1)
    temp.fill(roi)
    bounds = roi.getBounds()
    x0 = max(0, int(bounds.x))
    y0 = max(0, int(bounds.y))
    x1 = min(width, int(bounds.x + bounds.width))
    y1 = min(height, int(bounds.y + bounds.height))
    count = 0
    sum_x = 0.0
    sum_y = 0.0
    min_x = width
    min_y = height
    max_x = 0
    max_y = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if int(temp.getPixel(x, y)) > 0 and int(label_ip.getPixel(x, y)) == 0:
                label_ip.putPixel(x, y, int(bubble_id))
                count += 1
                sum_x += x
                sum_y += y
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if count == 0:
        return None
    return {
        "area_px": float(count),
        "centroid_x_px": sum_x / count,
        "centroid_y_px": sum_y / count,
        "bbox_x_px": float(min_x),
        "bbox_y_px": float(min_y),
        "bbox_width_px": float(max_x - min_x + 1),
        "bbox_height_px": float(max_y - min_y + 1),
        "touches_border": min_x <= 1 or min_y <= 1 or max_x >= width - 2 or max_y >= height - 2,
    }


def manual_measurement_row(bubble_id, stats, pixel_width, pixel_height, unit, calibration_status, calibration_source, quality_gate_mode):
    area_px = stats["area_px"]
    diameter_px = equivalent_diameter_from_area(area_px, 1.0, 1.0)
    diameter_calibrated = equivalent_diameter_from_area(area_px, pixel_width, pixel_height)
    trusted = calibration_status == "known"
    row = {
        "bubble_id": bubble_id,
        "score": 1.0,
        "area_px": area_px,
        "area_calibrated": area_px * pixel_width * pixel_height,
        "equivalent_diameter_px": diameter_px,
        "equivalent_diameter_calibrated": diameter_calibrated,
        "diameter_unit": unit,
        "calibration_status": calibration_status,
        "calibration_source": calibration_source,
        "physical_measurement_trusted": trusted,
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "centroid_x_px": stats["centroid_x_px"],
        "centroid_y_px": stats["centroid_y_px"],
        "bbox_x_px": stats["bbox_x_px"],
        "bbox_y_px": stats["bbox_y_px"],
        "bbox_width_px": stats["bbox_width_px"],
        "bbox_height_px": stats["bbox_height_px"],
        "touches_border": stats["touches_border"],
        "contains_saturated_highlight": "",
        "saturated_highlight_fraction": "",
        "low_confidence": False,
        "accepted": True,
        "measurement_status": "bubble",
        "accepted_for_histogram": True,
        "rejection_reason": "",
        "focus_score": "",
        "boundary_gradient_score": "",
        "annular_contrast": "",
        "circularity": "",
        "solidity": "",
        "eccentricity": "",
        "bbox_aspect_ratio": "",
        "perimeter_px": "",
        "quality_gate_mode": quality_gate_mode,
        "flags": "",
        "quality_flags": "",
    }
    return row


def add_manual_rois_to_overlay(imp, rois, first_id):
    overlay = imp.getOverlay()
    if overlay is None:
        overlay = Overlay()
    bubble_id = first_id
    for roi in rois:
        draw_roi = roi.clone()
        draw_roi.setStrokeColor(Color(46, 204, 113))
        draw_roi.setStrokeWidth(2)
        overlay.add(draw_roi)
        bounds = roi.getBounds()
        label = TextRoi(bounds.x, max(0, bounds.y - 12), str(bubble_id))
        label.setStrokeColor(Color(46, 204, 113))
        label.setFont(Font("SansSerif", Font.BOLD, 10))
        overlay.add(label)
        bubble_id += 1
    imp.setOverlay(overlay)
    imp.updateAndDraw()


def run_histogram_export_for_csv(measurements_csv, run_dir, prefix, image_id):
    script_path = BUBMASK_PROJECT + "\\src\\main\\python\\bubmask_fiji\\histogram\\histograms.py"
    pb = ProcessBuilder([
        BUBMASK_PYTHON,
        script_path,
        "--measurements-csv",
        measurements_csv,
        "--output-dir",
        run_dir.getAbsolutePath(),
        "--prefix",
        prefix,
        "--image-id",
        image_id,
    ])
    pb.directory(File(BUBMASK_PROJECT))
    process = pb.start()
    stdout = read_process_stream(process.getInputStream())
    stderr = read_process_stream(process.getErrorStream())
    exit_code = process.waitFor()
    if stdout:
        log_message("Manual-bubble histogram stdout:\n" + stdout)
    if stderr:
        log_message("Manual-bubble histogram stderr:\n" + stderr)
    return exit_code


def run_excel_export_for_csv(measurements_csv, output_xlsx):
    if measurements_csv is None or measurements_csv == "" or not File(measurements_csv).isFile():
        return 2
    script_path = BUBMASK_PROJECT + "\\src\\main\\python\\bubmask_fiji\\export\\excel_export.py"
    pb = ProcessBuilder([
        BUBMASK_PYTHON,
        script_path,
        "--input-csv",
        measurements_csv,
        "--output-xlsx",
        output_xlsx,
    ])
    pb.directory(File(BUBMASK_PROJECT))
    process = pb.start()
    stdout = read_process_stream(process.getInputStream())
    stderr = read_process_stream(process.getErrorStream())
    exit_code = process.waitFor()
    if stdout:
        log_message("Excel bubble-list export stdout:\n" + stdout)
    if stderr:
        log_message("Excel bubble-list export stderr:\n" + stderr)
    return exit_code


def parse_float_field(field, default_value):
    try:
        return float(str(field.getText()).strip())
    except Exception:
        return default_value


def parse_int_field(field, default_value):
    try:
        return int(float(str(field.getText()).strip()))
    except Exception:
        return default_value


def add_form_row(panel, row, label, component):
    left = GridBagConstraints()
    left.gridx = 0
    left.gridy = row
    left.anchor = GridBagConstraints.EAST
    left.insets = Insets(4, 4, 4, 8)
    panel.add(JLabel(label), left)
    right = GridBagConstraints()
    right.gridx = 1
    right.gridy = row
    right.fill = GridBagConstraints.HORIZONTAL
    right.weightx = 1.0
    right.insets = Insets(4, 4, 4, 4)
    panel.add(component, right)


class TogglePanelListener(ActionListener):
    def __init__(self, frame, panel, button):
        self.frame = frame
        self.panel = panel
        self.button = button

    def actionPerformed(self, event):
        visible = not self.panel.isVisible()
        self.panel.setVisible(visible)
        self.button.setText("Hide options" if visible else "More options")
        self.frame.pack()
        self.frame.setLocationRelativeTo(None)


class SettingsDoneListener(ActionListener):
    def __init__(self, state, frame, action):
        self.state = state
        self.frame = frame
        self.action = action

    def actionPerformed(self, event):
        self.state["action"] = self.action
        self.state["done"] = True
        self.frame.dispose()


def show_bubmask_settings_window():
    method_labels = [
        "Mask R-CNN bubble segmentation",
        "Adaptive threshold diagnostic",
        "Placeholder test",
    ]
    method_values = {
        method_labels[0]: "bubmask_mask_rcnn",
        method_labels[1]: "adaptive_threshold_baseline",
        method_labels[2]: "placeholder",
    }
    state = {"done": False, "action": "CANCEL"}
    frame = JFrame("BubMask Bubble Analyzer")
    frame.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE)

    root = JPanel(BorderLayout())
    header = JPanel()
    header.add(JLabel("BubMask Bubble Analyzer"))
    root.add(header, BorderLayout.NORTH)

    form = JPanel(GridBagLayout())
    method_choice = JComboBox(method_labels)
    model_choice = JComboBox(BUBMASK_MODEL_CHOICES)
    model_choice.setSelectedItem(BUBMASK_MODEL_CHOICES[2])
    confidence_field = JTextField("0.50", 10)
    calibration_field = JTextField("183.000", 10)
    add_form_row(form, 0, "Bubble detection method", method_choice)
    add_form_row(form, 1, "Model", model_choice)
    add_form_row(form, 2, "Confidence threshold", confidence_field)
    add_form_row(form, 3, "Calibration px/mm", calibration_field)

    advanced = JPanel(GridBagLayout())
    overlay_choice = JComboBox(["boxes_only", "masks_only", "boxes_and_masks"])
    overlay_choice.setSelectedItem("boxes_and_masks")
    preprocessing_choice = JComboBox(["raw_model", "fov_flatfield_model", "conservative_denoise_model", "classical_diagnostic"])
    quality_choice = JComboBox(["review_only", "filter_histogram", "off"])
    preview_choice = JComboBox(["comparison_only", "all_processing_images", "none"])
    sharp_checkbox = JCheckBox("Measure sharp bubbles only", False)
    focus_field = JTextField("10.0", 10)
    min_diameter_field = JTextField("0", 10)
    max_diameter_field = JTextField("0", 10)
    background_field = JTextField("", 28)
    background_choice = JComboBox(["none", "absolute_difference", "subtract_offset"])
    background_offset_field = JTextField("0.0", 10)
    add_form_row(advanced, 0, "Overlay display", overlay_choice)
    add_form_row(advanced, 1, "Preprocessing profile", preprocessing_choice)
    add_form_row(advanced, 2, "Quality gate mode", quality_choice)
    add_form_row(advanced, 3, "Processing previews", preview_choice)
    add_form_row(advanced, 4, "Sharp-bubble filter", sharp_checkbox)
    add_form_row(advanced, 5, "Minimum focus score", focus_field)
    add_form_row(advanced, 6, "Minimum diameter px", min_diameter_field)
    add_form_row(advanced, 7, "Maximum diameter px", max_diameter_field)
    add_form_row(advanced, 8, "Background image path", background_field)
    add_form_row(advanced, 9, "Background correction", background_choice)
    add_form_row(advanced, 10, "Background offset", background_offset_field)
    advanced.setVisible(False)

    center = JPanel(BorderLayout())
    center.add(form, BorderLayout.NORTH)
    center.add(advanced, BorderLayout.CENTER)
    root.add(center, BorderLayout.CENTER)

    buttons = JPanel()
    back_button = JButton("BACK")
    back_button.setEnabled(False)
    more_button = JButton("More options")
    next_button = JButton("NEXT/OK")
    cancel_button = JButton("CANCEL")
    more_button.addActionListener(TogglePanelListener(frame, advanced, more_button))
    next_button.addActionListener(SettingsDoneListener(state, frame, "NEXT"))
    cancel_button.addActionListener(SettingsDoneListener(state, frame, "CANCEL"))
    buttons.add(back_button)
    buttons.add(more_button)
    buttons.add(next_button)
    buttons.add(cancel_button)
    root.add(buttons, BorderLayout.SOUTH)

    frame.getContentPane().add(root, BorderLayout.CENTER)
    frame.pack()
    frame.setLocationRelativeTo(None)
    frame.setVisible(True)
    while not state["done"]:
        Thread.sleep(200)
    if state["action"] == "CANCEL":
        return None

    method_label = str(method_choice.getSelectedItem())
    calibration = parse_float_field(calibration_field, 183.0)
    if calibration <= 0:
        calibration = 183.0
    return {
        "method_choice": method_label,
        "inference_mode": method_values.get(method_label, "bubmask_mask_rcnn"),
        "model_choice": str(model_choice.getSelectedItem()),
        "confidence": parse_float_field(confidence_field, 0.5),
        "manual_px_per_mm": calibration,
        "overlay_mode": str(overlay_choice.getSelectedItem()),
        "preprocessing_profile": str(preprocessing_choice.getSelectedItem()),
        "quality_gate_mode": str(quality_choice.getSelectedItem()),
        "processing_preview_mode": str(preview_choice.getSelectedItem()),
        "measure_sharp_only": sharp_checkbox.isSelected(),
        "min_focus_score": parse_float_field(focus_field, 10.0),
        "min_diameter_px": parse_float_field(min_diameter_field, 0.0),
        "max_diameter_px": parse_float_field(max_diameter_field, 0.0),
        "background_image_path": str(background_field.getText()).strip(),
        "background_correction_mode": str(background_choice.getSelectedItem()),
        "background_offset": parse_float_field(background_offset_field, 0.0),
    }


def export_manual_bubble_artifacts(imp, outputs, measurements, run_dir, manual_rois, pixel_width, pixel_height, unit, calibration_status, calibration_source, quality_gate_mode):
    if len(manual_rois) == 0:
        return 0
    width = imp.getWidth()
    height = imp.getHeight()
    label_ip = get_label_processor(outputs, width, height)
    next_id = max(max_label_value(label_ip), measurements.length()) + 1
    manual_rows = []
    kept_rois = []
    for roi in manual_rois:
        stats = measure_and_add_roi_to_label(label_ip, roi, next_id)
        if stats is None:
            log_message("Manual bubble ROI skipped because it added no new mask pixels.")
            continue
        manual_rows.append(manual_measurement_row(
            next_id,
            stats,
            pixel_width,
            pixel_height,
            unit,
            calibration_status,
            calibration_source,
            quality_gate_mode,
        ))
        kept_rois.append(roi)
        next_id += 1
    if len(manual_rows) == 0:
        return 0

    manual_csv = File(run_dir, "manual_added_bubbles.csv").getAbsolutePath()
    combined_csv = File(run_dir, "per_bubble_measurements_with_manual.csv").getAbsolutePath()
    combined_xlsx = File(run_dir, "bubble_measurements_with_manual.xlsx").getAbsolutePath()
    manual_label_tif = File(run_dir, "instance_labels_with_manual.tif").getAbsolutePath()
    manual_overlay_png = File(run_dir, "overlay_with_manual_bubbles.png").getAbsolutePath()

    original_csv = outputs.optString("per_bubble_csv") if outputs is not None else ""
    fieldnames, original_rows = read_csv_rows(original_csv)
    if len(fieldnames) == 0:
        fieldnames = [
            "bubble_id", "score", "area_px", "area_calibrated",
            "equivalent_diameter_px", "equivalent_diameter_calibrated",
            "diameter_unit", "calibration_status", "calibration_source",
            "physical_measurement_trusted", "pixel_width", "pixel_height",
            "centroid_x_px", "centroid_y_px", "bbox_x_px", "bbox_y_px",
            "bbox_width_px", "bbox_height_px", "touches_border",
            "low_confidence", "accepted", "measurement_status",
            "accepted_for_histogram", "rejection_reason", "quality_gate_mode",
            "flags", "quality_flags",
        ]
    for row in manual_rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    for row in original_rows:
        row["measurement_status"] = "bubble"
        row["accepted"] = "True"
        row["accepted_for_histogram"] = "True"
        row["rejection_reason"] = ""
        row["flags"] = ""
        row["quality_flags"] = ""

    write_csv_rows(manual_csv, fieldnames, manual_rows)
    write_csv_rows(combined_csv, fieldnames, original_rows + manual_rows)
    excel_exit = run_excel_export_for_csv(combined_csv, combined_xlsx)
    if excel_exit != 0:
        log_message("Manual-bubble Excel export failed with exit code " + str(excel_exit))
    manual_imp = ImagePlus("BubMask instance labels with manual bubbles", label_ip)
    IJ.saveAs(manual_imp, "Tiff", manual_label_tif)

    first_manual_id = int(manual_rows[0].get("bubble_id", 1))
    add_manual_rois_to_overlay(imp, kept_rois, first_manual_id)
    base_mask_path = outputs.optString("overlay_masks_png") if outputs is not None else ""
    base_mask_imp = IJ.openImage(base_mask_path) if base_mask_path and File(base_mask_path).isFile() else None
    if base_mask_imp is not None:
        add_manual_rois_to_overlay(base_mask_imp, kept_rois, first_manual_id)
        flattened = base_mask_imp.flatten()
    else:
        flattened = imp.flatten()
    IJ.saveAs(flattened, "PNG", manual_overlay_png)
    flattened.close()
    if base_mask_imp is not None:
        base_mask_imp.close()

    hist_exit = run_histogram_export_for_csv(
        combined_csv,
        run_dir,
        "diameter_with_manual",
        imp.getTitle(),
    )
    if hist_exit != 0:
        log_message("Manual-bubble histogram export failed with exit code " + str(hist_exit))

    add_output_row(outputs_rt, "manual bubbles CSV", manual_csv)
    add_output_row(outputs_rt, "per-bubble CSV with manual bubbles", combined_csv)
    add_output_row(outputs_rt, "bubble list Excel with manual bubbles", combined_xlsx)
    add_output_row(outputs_rt, "instance labels with manual bubbles TIFF", manual_label_tif)
    add_output_row(outputs_rt, "overlay with manual bubbles PNG", manual_overlay_png)
    add_output_row(outputs_rt, "with-manual histogram all CSV", File(run_dir, "diameter_with_manual_histogram_all.csv").getAbsolutePath())
    add_output_row(outputs_rt, "with-manual histogram all PNG", File(run_dir, "diameter_with_manual_histogram_all.png").getAbsolutePath())
    add_output_row(outputs_rt, "with-manual accepted histogram CSV", File(run_dir, "diameter_with_manual_histogram_accepted.csv").getAbsolutePath())
    add_output_row(outputs_rt, "with-manual accepted histogram PNG", File(run_dir, "diameter_with_manual_histogram_accepted.png").getAbsolutePath())
    add_output_row(outputs_rt, "with-manual raw-vs-reconstructed histogram CSV", File(run_dir, "diameter_with_manual_histogram_raw_vs_reconstructed.csv").getAbsolutePath())
    add_output_row(outputs_rt, "with-manual raw-vs-reconstructed histogram PNG", File(run_dir, "diameter_with_manual_histogram_raw_vs_reconstructed.png").getAbsolutePath())
    add_output_row(outputs_rt, "with-manual histogram summary JSON", File(run_dir, "diameter_with_manual_histogram_summary.json").getAbsolutePath())
    return len(manual_rows)


def prompt_mask_review_choice():
    dialog = GenericDialogPlus("BubMask Mask Review")
    dialog.addMessage("BubMask mask overlay is ready. Add manual bubble or proceed?")
    dialog.addChoice(
        "Next step",
        ["PROCEED TO HISTOGRAM", "ADD MANUAL BUBBLE"],
        "PROCEED TO HISTOGRAM",
    )
    dialog.showDialog()
    if dialog.wasCanceled():
        return "PROCEED TO HISTOGRAM"
    return dialog.getNextChoice()


def display_row_from_manual_row(row):
    return [
        display_value(row.get("bubble_id")),
        "bubble",
        "True",
        display_value(row.get("score")),
        display_value(row.get("equivalent_diameter_calibrated")),
        display_value(row.get("diameter_unit")),
        display_value(row.get("area_px")),
        display_value(row.get("centroid_x_px")),
        display_value(row.get("centroid_y_px")),
        "",
        "",
    ]


def review_table_row(display_row):
    return [
        display_row[0],
        "bubble",
        display_row[4],
        display_row[5],
        display_row[6],
        display_row[7],
        display_row[8],
    ]


def add_review_model_row(model, display_row):
    model.addRow(review_table_row(display_row))


def add_single_roi_to_review_state(state, roi):
    if roi is None:
        log_message("No ROI selected. Draw a Fiji ROI around the missed bubble, then click Add current ROI.")
        return False
    bubble_id = state["next_id"]
    stats = measure_and_add_roi_to_label(state["label_ip"], roi, bubble_id)
    if stats is None:
        log_message("ROI skipped because it does not add new bubble pixels.")
        return False
    row = manual_measurement_row(
        bubble_id,
        stats,
        state["pixel_width"],
        state["pixel_height"],
        state["unit"],
        state["calibration_status"],
        state["calibration_source"],
        state["quality_gate_mode"],
    )
    state["manual_rois"].append(roi.clone())
    state["manual_rows"].append(row)
    state["next_id"] = bubble_id + 1
    display_row = display_row_from_manual_row(row)
    MEASUREMENT_ROWS.append(display_row)
    add_review_model_row(state["model"], display_row)
    add_manual_rois_to_overlay(state["imp"], [roi], bubble_id)
    state["message"].setText("Added bubble " + str(bubble_id) + ". Draw another ROI or press NEXT.")
    return True


def create_manual_review_state(imp, outputs, measurements, pixel_width, pixel_height, unit, calibration_status, calibration_source, quality_gate_mode):
    label_ip = get_label_processor(outputs, imp.getWidth(), imp.getHeight())
    model = DefaultTableModel()
    for col in ["ID", "Status", "Diameter", "Unit", "Area px", "X px", "Y px"]:
        model.addColumn(col)
    for row in MEASUREMENT_ROWS:
        add_review_model_row(model, row)
    return {
        "imp": imp,
        "outputs": outputs,
        "measurements": measurements,
        "label_ip": label_ip,
        "next_id": max(max_label_value(label_ip), measurements.length()) + 1,
        "manual_rois": [],
        "manual_rows": [],
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "unit": unit,
        "calibration_status": calibration_status,
        "calibration_source": calibration_source,
        "quality_gate_mode": quality_gate_mode,
        "model": model,
        "done": False,
        "cancelled": False,
        "message": JLabel("Draw a Fiji ROI around a missed bubble, then click Add current ROI."),
    }


class AddCurrentRoiListener(ActionListener):
    def __init__(self, state):
        self.state = state

    def actionPerformed(self, event):
        try:
            current = IJ.getImage()
            roi = current.getRoi() if current is not None else self.state["imp"].getRoi()
            add_single_roi_to_review_state(self.state, roi.clone() if roi is not None else None)
        except Exception as exc:
            log_message("Could not add current ROI: " + str(exc))


class AddRoiManagerListener(ActionListener):
    def __init__(self, state):
        self.state = state

    def actionPerformed(self, event):
        try:
            manager = RoiManager.getInstance()
            if manager is None or manager.getCount() == 0:
                self.state["message"].setText("ROI Manager is empty.")
                return
            added = 0
            roi_array = manager.getRoisAsArray()
            for roi in roi_array:
                if add_single_roi_to_review_state(self.state, roi.clone()):
                    added += 1
            self.state["message"].setText("Added " + str(added) + " ROI Manager bubbles. Press NEXT when ready.")
        except Exception as exc:
            log_message("Could not add ROI Manager ROIs: " + str(exc))


class NextReviewListener(ActionListener):
    def __init__(self, state, frame):
        self.state = state
        self.frame = frame

    def actionPerformed(self, event):
        self.state["done"] = True
        self.frame.dispose()


class CancelReviewListener(ActionListener):
    def __init__(self, state, frame):
        self.state = state
        self.frame = frame

    def actionPerformed(self, event):
        self.state["cancelled"] = True
        self.state["done"] = True
        self.frame.dispose()


def show_manual_bubble_review_window(state):
    frame = JFrame("BubMask Manual Bubble Review")
    frame.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE)
    table = JTable(state["model"])
    top = JPanel()
    top.add(JLabel("Use Fiji ROI tools on the mask overlay. Each added ROI becomes a bubble."))
    bottom = JPanel()
    add_current = JButton("Add current ROI")
    add_manager = JButton("Add ROI Manager ROIs")
    back_button = JButton("BACK")
    next_button = JButton("NEXT/OK")
    cancel_button = JButton("CANCEL")
    add_current.addActionListener(AddCurrentRoiListener(state))
    add_manager.addActionListener(AddRoiManagerListener(state))
    back_button.addActionListener(NextReviewListener(state, frame))
    next_button.addActionListener(NextReviewListener(state, frame))
    cancel_button.addActionListener(CancelReviewListener(state, frame))
    bottom.add(add_current)
    bottom.add(add_manager)
    bottom.add(back_button)
    bottom.add(next_button)
    bottom.add(cancel_button)
    frame.getContentPane().add(top, BorderLayout.NORTH)
    frame.getContentPane().add(JScrollPane(table), BorderLayout.CENTER)
    status_panel = JPanel()
    status_panel.add(state["message"])
    status_panel.add(bottom)
    frame.getContentPane().add(status_panel, BorderLayout.SOUTH)
    frame.setSize(780, 620)
    frame.setLocation(900, 60)
    frame.setVisible(True)
    while not state["done"]:
        Thread.sleep(200)
    state["done"] = False
    if state.get("cancelled", False):
        raise SystemExit


def histogram_png_for_review(outputs, run_dir, manual_count):
    if manual_count > 0:
        path = File(run_dir, "diameter_with_manual_histogram_all.png").getAbsolutePath()
        if File(path).isFile():
            return path
    if outputs is not None:
        path = outputs.optString("diameter_histogram_all_png")
        if path and File(path).isFile():
            return path
    return ""


def histogram_csv_for_review(outputs, run_dir, manual_count):
    if manual_count > 0:
        path = File(run_dir, "per_bubble_measurements_with_manual.csv").getAbsolutePath()
        if File(path).isFile():
            return path
    if outputs is not None:
        path = outputs.optString("per_bubble_csv")
        if path and File(path).isFile():
            return path
    return ""


def add_analysis_table_row(model, row, unit_default):
    bubble_id = row.get("bubble_id", "")
    accepted = row.get("accepted_for_histogram", row.get("accepted", "True"))
    diameter = row.get("equivalent_diameter_calibrated", row.get("equivalent_diameter_px", row.get("diameter", "")))
    unit = row.get("diameter_unit", row.get("unit", unit_default))
    area = row.get("area_px", "")
    score = row.get("score", "")
    model.addRow([display_value(accepted), display_value(bubble_id), display_value(diameter), display_value(unit), display_value(area), display_value(score)])


def create_analysis_table_model(source_csv):
    model = DefaultTableModel()
    for col in ["Use", "ID", "Diameter", "Unit", "Area px", "Score"]:
        model.addColumn(col)
    fieldnames, rows = read_csv_rows(source_csv)
    unit_default = "pixel"
    for row in rows:
        unit_default = row.get("diameter_unit", row.get("unit", unit_default))
        add_analysis_table_row(model, row, unit_default)
    return model


def write_analysis_input_csv(path, model):
    lines = ["accepted_for_histogram,bubble_id,diameter,diameter_unit,area_px,score"]
    for row_index in range(model.getRowCount()):
        values = []
        for col_index in range(model.getColumnCount()):
            values.append(display_value(model.getValueAt(row_index, col_index)))
        lines.append(",".join([csv_escape(value) for value in values]))
    write_text(path, "\n".join(lines) + "\n")


def read_stats_summary(path):
    if path is None or path == "" or not File(path).isFile():
        return "No statistics generated yet."
    fieldnames, rows = read_csv_rows(path)
    lines = ["Metric\tValue\tUnit"]
    for row in rows:
        lines.append(display_value(row.get("metric")) + "\t" + display_value(row.get("value")) + "\t" + display_value(row.get("unit")))
    return "\n".join(lines)


def set_image_preview(label, path, fallback):
    if path and File(path).isFile():
        label.setIcon(ImageIcon(path))
        label.setText("")
    else:
        label.setIcon(None)
        label.setText(fallback)


def image_preview_panel(title, image_label):
    panel = JPanel(BorderLayout())
    heading = JLabel(title)
    heading.setFont(Font("SansSerif", Font.BOLD, 13))
    panel.add(heading, BorderLayout.NORTH)
    panel.add(JScrollPane(image_label), BorderLayout.CENTER)
    return panel


def output_path(outputs, key):
    if outputs is None:
        return ""
    return outputs.optString(key)


def initial_mask_overlay_path(outputs, run_dir):
    manual_preview = File(run_dir, "overlay_with_manual_bubbles_preview.png").getAbsolutePath()
    if File(manual_preview).isFile():
        return manual_preview
    manual_final = File(run_dir, "overlay_with_manual_bubbles.png").getAbsolutePath()
    if File(manual_final).isFile():
        return manual_final
    return output_path(outputs, "overlay_masks_png")


def base_mask_overlay_path(outputs):
    return output_path(outputs, "overlay_masks_png")


def open_manual_overlay_window(outputs, run_dir):
    path = initial_mask_overlay_path(outputs, run_dir)
    overlay_imp = IJ.openImage(path) if path and File(path).isFile() else None
    if overlay_imp is None:
        log_message("Manual overlay review image could not be opened.")
        return None
    overlay_imp.setTitle("BubMask Overlay Review - draw Fiji ROI here")
    overlay_imp.show()
    try:
        if overlay_imp.getWindow() is not None:
            overlay_imp.getWindow().setLocation(20, 60)
    except Exception:
        pass
    log_message("Opened manual ROI overlay window: " + path)
    return overlay_imp


def update_manual_overlay_window(manual_state, path):
    overlay_imp = manual_state.get("overlay_review_imp")
    if overlay_imp is None or not path or not File(path).isFile():
        return False
    updated = IJ.openImage(path)
    if updated is None:
        return False
    try:
        overlay_imp.setProcessor(overlay_imp.getTitle(), updated.getProcessor())
        overlay_imp.updateAndDraw()
        if overlay_imp.getWindow() is None:
            overlay_imp.show()
        if overlay_imp.getWindow() is not None:
            overlay_imp.getWindow().toFront()
        return True
    finally:
        updated.close()


def refresh_manual_overlay_preview(manual_state, run_dir):
    preview_path = File(run_dir, "overlay_with_manual_bubbles_preview.png").getAbsolutePath()
    try:
        base_path = base_mask_overlay_path(manual_state.get("outputs"))
        if not base_path or not File(base_path).isFile():
            base_path = initial_mask_overlay_path(manual_state.get("outputs"), run_dir)
        base_imp = IJ.openImage(base_path) if base_path and File(base_path).isFile() else None
        if base_imp is not None:
            first_id = manual_state["next_id"] - len(manual_state["manual_rois"])
            add_manual_rois_to_overlay(base_imp, manual_state["manual_rois"], first_id)
            flattened = base_imp.flatten()
        else:
            flattened = manual_state["imp"].flatten()
        IJ.saveAs(flattened, "PNG", preview_path)
        flattened.close()
        if base_imp is not None:
            base_imp.close()
        update_manual_overlay_window(manual_state, preview_path)
        log_message("Manual mask overlay preview refreshed: " + preview_path)
        return preview_path
    except Exception as exc:
        log_message("Could not refresh manual mask overlay preview: " + str(exc))
        return initial_mask_overlay_path(manual_state.get("outputs"), run_dir)


def refresh_analysis_model_from_measurement_rows(model):
    model.setRowCount(0)
    for row in MEASUREMENT_ROWS:
        model.addRow([
            display_value(row[2] if len(row) > 2 else "True"),
            display_value(row[0] if len(row) > 0 else ""),
            display_value(row[4] if len(row) > 4 else ""),
            display_value(row[5] if len(row) > 5 else ""),
            display_value(row[6] if len(row) > 6 else ""),
            display_value(row[3] if len(row) > 3 else ""),
        ])


def run_interactive_histogram_export(input_csv, run_dir, prefix, bins, xmin, xmax, hist_by, show_pdf, show_cdf, show_d32, show_mean, show_d23):
    script_path = BUBMASK_PROJECT + "\\src\\main\\python\\bubmask_fiji\\histogram\\interactive_histogram.py"
    args = [
        BUBMASK_PYTHON,
        script_path,
        "--input-csv",
        input_csv,
        "--output-dir",
        run_dir.getAbsolutePath(),
        "--prefix",
        prefix,
        "--bins",
        str(bins),
        "--xmin",
        str(xmin),
        "--xmax",
        str(xmax),
        "--hist-by",
        hist_by,
    ]
    if show_pdf:
        args.append("--show-pdf")
    if show_cdf:
        args.append("--show-cdf")
    if show_d32:
        args.append("--show-d32")
    if show_mean:
        args.append("--show-mean")
    if show_d23:
        args.append("--show-d23")
    pb = ProcessBuilder(args)
    pb.directory(File(BUBMASK_PROJECT))
    process = pb.start()
    stdout = read_process_stream(process.getInputStream())
    stderr = read_process_stream(process.getErrorStream())
    exit_code = process.waitFor()
    if stdout:
        log_message("Interactive histogram stdout:\n" + stdout)
    if stderr:
        log_message("Interactive histogram stderr:\n" + stderr)
    return exit_code


def histogram_analysis_paths(run_dir, prefix):
    return (
        File(run_dir, prefix + ".png").getAbsolutePath(),
        File(run_dir, prefix + ".csv").getAbsolutePath(),
        File(run_dir, prefix + "_statistics.csv").getAbsolutePath(),
        File(run_dir, prefix + "_summary.json").getAbsolutePath(),
    )


def generate_histogram_analysis(state):
    prefix = str(state["prefix_field"].getText()).strip()
    if prefix == "":
        prefix = "histogram_analysis"
    input_csv = File(state["run_dir"], prefix + "_edited_input.csv").getAbsolutePath()
    write_analysis_input_csv(input_csv, state["table_model"])
    bins = max(1, parse_int_field(state["bins_field"], 15))
    xmin = parse_float_field(state["xmin_field"], 0.0)
    xmax = parse_float_field(state["xmax_field"], 0.0)
    hist_by_label = str(state["hist_by"].getSelectedItem())
    hist_by_map = {
        "Count": "count",
        "Fraction": "fraction",
        "Probability density": "density",
    }
    hist_by = hist_by_map.get(hist_by_label, "count")
    exit_code = run_interactive_histogram_export(
        input_csv,
        state["run_dir"],
        prefix,
        bins,
        xmin,
        xmax,
        hist_by,
        state["pdf_checkbox"].isSelected(),
        state["cdf_checkbox"].isSelected(),
        state["d32_checkbox"].isSelected(),
        state["mean_checkbox"].isSelected(),
        state["d23_checkbox"].isSelected(),
    )
    graph_png, hist_csv, stats_csv, summary_json = histogram_analysis_paths(state["run_dir"], prefix)
    if exit_code != 0 or not File(graph_png).isFile():
        state["message"].setText("Histogram analysis failed. See Log tab for details.")
        return False
    add_output_row(outputs_rt, "interactive histogram PNG", graph_png)
    add_output_row(outputs_rt, "interactive histogram CSV", hist_csv)
    add_output_row(outputs_rt, "interactive histogram statistics CSV", stats_csv)
    add_output_row(outputs_rt, "interactive histogram summary JSON", summary_json)
    add_output_row(outputs_rt, "interactive histogram edited input CSV", input_csv)
    state["stats_area"].setText(read_stats_summary(stats_csv))
    if state.get("histogram_image_label") is not None:
        set_image_preview(state["histogram_image_label"], graph_png, "No histogram image available.")
    if not state.get("suppress_open", False):
        IJ.open(graph_png)
    state["message"].setText("Generated " + File(graph_png).getName())
    return True


class HistogramAnalysisButtonListener(ActionListener):
    def __init__(self, state, frame, action):
        self.state = state
        self.frame = frame
        self.action = action

    def actionPerformed(self, event):
        if self.action == "NEXT":
            if not generate_histogram_analysis(self.state):
                return
        self.state["action"] = self.action
        self.state["done"] = True
        self.frame.dispose()


def refresh_central_text_tabs(state):
    if state.get("output_area") is not None:
        state["output_area"].setText(format_rows(["Artifact", "Path or status"], OUTPUT_ROWS))
    if state.get("log_area") is not None:
        state["log_area"].setText("\n".join(LOG_LINES))
    if state.get("summary_area") is not None:
        state["summary_area"].setText(format_rows(["Section", "Field", "Value"], SUMMARY_ROWS))


def current_manual_roi(manual_state):
    roi = None
    try:
        current = IJ.getImage()
        if current is not None:
            roi = current.getRoi()
    except Exception:
        roi = None
    if roi is None and manual_state.get("overlay_review_imp") is not None:
        roi = manual_state["overlay_review_imp"].getRoi()
    if roi is None:
        roi = manual_state["imp"].getRoi()
    return roi


class CentralAddCurrentRoiListener(ActionListener):
    def __init__(self, manual_state, central_state):
        self.manual_state = manual_state
        self.central_state = central_state

    def actionPerformed(self, event):
        try:
            roi = current_manual_roi(self.manual_state)
            if add_single_roi_to_review_state(self.manual_state, roi.clone() if roi is not None else None):
                refresh_analysis_model_from_measurement_rows(self.central_state["table_model"])
                self.central_state["message"].setText("Manual bubble added. Press Refresh mask overlay to update the preview.")
        except Exception as exc:
            log_message("Could not add current ROI: " + str(exc))
            self.central_state["message"].setText("Could not add current ROI. See Log tab.")
        refresh_central_text_tabs(self.central_state)


class CentralAddRoiManagerListener(ActionListener):
    def __init__(self, manual_state, central_state):
        self.manual_state = manual_state
        self.central_state = central_state

    def actionPerformed(self, event):
        try:
            manager = RoiManager.getInstance()
            if manager is None or manager.getCount() == 0:
                self.manual_state["message"].setText("ROI Manager is empty.")
                self.central_state["message"].setText("ROI Manager is empty.")
                return
            added = 0
            roi_array = manager.getRoisAsArray()
            for roi in roi_array:
                if add_single_roi_to_review_state(self.manual_state, roi.clone()):
                    added += 1
            refresh_analysis_model_from_measurement_rows(self.central_state["table_model"])
            self.manual_state["message"].setText("Added " + str(added) + " ROI Manager bubbles.")
            self.central_state["message"].setText("Added " + str(added) + " ROI Manager bubbles. Press Refresh mask overlay to update the preview.")
        except Exception as exc:
            log_message("Could not add ROI Manager ROIs: " + str(exc))
            self.central_state["message"].setText("Could not add ROI Manager ROIs. See Log tab.")
        refresh_central_text_tabs(self.central_state)


class CentralRefreshMaskOverlayListener(ActionListener):
    def __init__(self, manual_state, central_state):
        self.manual_state = manual_state
        self.central_state = central_state

    def actionPerformed(self, event):
        path = refresh_manual_overlay_preview(self.manual_state, self.central_state["run_dir"])
        refresh_analysis_model_from_measurement_rows(self.central_state["table_model"])
        self.central_state["message"].setText(
            "Overlay window refreshed with " + str(len(self.manual_state["manual_rois"])) + " manual bubbles."
        )
        refresh_central_text_tabs(self.central_state)


class CentralBackListener(ActionListener):
    def __init__(self, state):
        self.state = state

    def actionPerformed(self, event):
        tabs = self.state["tabs"]
        index = tabs.getSelectedIndex()
        if index > 0:
            tabs.setSelectedIndex(index - 1)
            self.state["message"].setText("Returned to " + tabs.getTitleAt(index - 1) + ".")
        else:
            self.state["message"].setText("Already at the first step.")


class CentralCancelListener(ActionListener):
    def __init__(self, state, frame):
        self.state = state
        self.frame = frame

    def actionPerformed(self, event):
        self.state["action"] = "CANCEL"
        self.state["done"] = True
        self.frame.dispose()


def export_manual_review_if_needed(manual_state, state):
    manual_count = state.get("manual_count", 0)
    roi_count = len(manual_state["manual_rois"])
    if roi_count > 0 and state.get("manual_exported_roi_count", -1) != roi_count:
        manual_count = export_manual_bubble_artifacts(
            manual_state["imp"],
            manual_state["outputs"],
            manual_state["measurements"],
            state["run_dir"],
            manual_state["manual_rois"],
            manual_state["pixel_width"],
            manual_state["pixel_height"],
            manual_state["unit"],
            manual_state["calibration_status"],
            manual_state["calibration_source"],
            manual_state["quality_gate_mode"],
        )
        add_summary_row(summary_rt, "Manual bubbles", "added to mask", manual_count)
        final_overlay = File(state["run_dir"], "overlay_with_manual_bubbles.png").getAbsolutePath()
        update_manual_overlay_window(manual_state, final_overlay)
        refresh_analysis_model_from_measurement_rows(state["table_model"])
        state["manual_exported_roi_count"] = roi_count
    state["manual_count"] = manual_count
    refresh_central_text_tabs(state)
    return manual_count


class CentralNextTabListener(ActionListener):
    def __init__(self, state):
        self.state = state

    def actionPerformed(self, event):
        tabs = self.state["tabs"]
        index = tabs.getSelectedIndex()
        if index < tabs.getTabCount() - 1:
            tabs.setSelectedIndex(index + 1)
            self.state["message"].setText("Moved to " + tabs.getTitleAt(index + 1) + ".")
        else:
            self.state["message"].setText("Already at the last review tab. Press FINISH PROCESSING when ready.")


class CentralOkListener(ActionListener):
    def __init__(self, manual_state, state, frame):
        self.manual_state = manual_state
        self.state = state
        self.frame = frame

    def actionPerformed(self, event):
        tab_title = self.state["tabs"].getTitleAt(self.state["tabs"].getSelectedIndex())
        if tab_title == "Manual Bubbles":
            refresh_manual_overlay_preview(self.manual_state, self.state["run_dir"])
            refresh_analysis_model_from_measurement_rows(self.state["table_model"])
            self.state["message"].setText("Manual overlay/table refreshed.")
            refresh_central_text_tabs(self.state)
            return
        export_manual_review_if_needed(self.manual_state, self.state)
        if not generate_histogram_analysis(self.state):
            refresh_central_text_tabs(self.state)
            return
        self.state["message"].setText("Histogram refreshed. Change settings and press OK again, or press FINISH PROCESSING.")
        refresh_central_text_tabs(self.state)


class CentralFinishListener(ActionListener):
    def __init__(self, manual_state, state, frame):
        self.manual_state = manual_state
        self.state = state
        self.frame = frame

    def actionPerformed(self, event):
        export_manual_review_if_needed(self.manual_state, self.state)
        if not generate_histogram_analysis(self.state):
            refresh_central_text_tabs(self.state)
            return
        refresh_central_text_tabs(self.state)
        self.state["action"] = "FINISH"
        self.state["done"] = True
        self.frame.dispose()


class CentralChangeModelListener(ActionListener):
    def __init__(self, manual_state, state, frame):
        self.manual_state = manual_state
        self.state = state
        self.frame = frame

    def actionPerformed(self, event):
        overlay_imp = self.manual_state.get("overlay_review_imp")
        if overlay_imp is not None:
            try:
                overlay_imp.close()
            except Exception:
                pass
        self.state["action"] = "CHANGE_MODEL"
        self.state["done"] = True
        self.frame.dispose()


def show_central_bubmask_review_window(manual_state, outputs, run_dir):
    source_csv = histogram_csv_for_review(outputs, run_dir, 0)
    if source_csv == "":
        table_model = DefaultTableModel()
        for col in ["Use", "ID", "Diameter", "Unit", "Area px", "Score"]:
            table_model.addColumn(col)
        refresh_analysis_model_from_measurement_rows(table_model)
    else:
        table_model = create_analysis_table_model(source_csv)

    state = {
        "done": False,
        "action": "CANCEL",
        "manual_count": 0,
        "manual_exported_roi_count": -1,
        "run_dir": run_dir,
        "table_model": table_model,
        "suppress_open": True,
    }
    frame = JFrame("BubMask Review and Analysis")
    frame.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE)
    root = JPanel(BorderLayout())
    message = JLabel("Draw Fiji ROIs in the separate overlay window; use this window to add ROIs, review data, and generate histogram/statistics.")
    message.setFont(Font("SansSerif", Font.PLAIN, 13))
    root.add(message, BorderLayout.NORTH)
    state["message"] = message

    tabs = JTabbedPane()
    state["tabs"] = tabs

    manual_state["overlay_review_imp"] = open_manual_overlay_window(outputs, run_dir)
    histogram_label = JLabel()
    state["histogram_image_label"] = histogram_label
    set_image_preview(histogram_label, histogram_png_for_review(outputs, run_dir, 0), "No histogram image available yet.")

    manual_tab = JPanel(BorderLayout())
    manual_top = JPanel(BorderLayout())
    manual_top.add(manual_state["message"], BorderLayout.CENTER)
    manual_tab.add(manual_top, BorderLayout.NORTH)
    manual_table = JTable(manual_state["model"])
    manual_tab.add(JScrollPane(manual_table), BorderLayout.CENTER)
    manual_buttons = JPanel()
    add_current = JButton("Add current ROI")
    add_manager = JButton("Add ROI Manager ROIs")
    refresh_manual_button = JButton("Refresh mask overlay")
    manual_buttons.add(add_current)
    manual_buttons.add(add_manager)
    manual_buttons.add(refresh_manual_button)
    manual_tab.add(manual_buttons, BorderLayout.SOUTH)
    tabs.addTab("Manual Bubbles", manual_tab)

    controls = JPanel(GridBagLayout())
    hist_by = JComboBox(["Count", "Fraction", "Probability density"])
    bins_field = JTextField("15", 8)
    xmin_field = JTextField("0.0", 8)
    xmax_field = JTextField("0.0", 8)
    pdf_checkbox = JCheckBox("PDF", False)
    cdf_checkbox = JCheckBox("CDF", False)
    d32_checkbox = JCheckBox("D32 / Sauter mean", True)
    mean_checkbox = JCheckBox("Mean diameter", True)
    d23_checkbox = JCheckBox("D23 marker", False)
    prefix_field = JTextField("histogram_analysis", 18)
    add_form_row(controls, 0, "Histogram by", hist_by)
    add_form_row(controls, 1, "Number of bins", bins_field)
    add_form_row(controls, 2, "X-axis minimum", xmin_field)
    add_form_row(controls, 3, "X-axis maximum", xmax_field)
    add_form_row(controls, 4, "Show PDF", pdf_checkbox)
    add_form_row(controls, 5, "Show CDF", cdf_checkbox)
    add_form_row(controls, 6, "Show D32", d32_checkbox)
    add_form_row(controls, 7, "Show mean", mean_checkbox)
    add_form_row(controls, 8, "Show D23", d23_checkbox)
    add_form_row(controls, 9, "Output prefix", prefix_field)

    histogram_tab = JPanel(BorderLayout())
    histogram_tab.add(image_preview_panel("Histogram preview", histogram_label), BorderLayout.CENTER)
    histogram_tab.add(JScrollPane(controls), BorderLayout.EAST)
    tabs.addTab("Histogram", histogram_tab)

    bubble_table = JTable(table_model)
    tabs.addTab("Bubble Table", JScrollPane(bubble_table))

    stats_area = JTextArea("Press OK to refresh the graph and statistics. Press FINISH PROCESSING only when ready to export files.")
    stats_area.setEditable(False)
    stats_area.setFont(Font("Monospaced", Font.PLAIN, 12))
    tabs.addTab("Statistics", JScrollPane(stats_area))

    summary_area = JTextArea(format_rows(["Section", "Field", "Value"], SUMMARY_ROWS))
    summary_area.setEditable(False)
    summary_area.setFont(Font("Monospaced", Font.PLAIN, 12))
    tabs.addTab("Run Summary", JScrollPane(summary_area))

    log_area = JTextArea("\n".join(LOG_LINES))
    log_area.setEditable(False)
    log_area.setFont(Font("Monospaced", Font.PLAIN, 12))
    tabs.addTab("Log", JScrollPane(log_area))

    state.update({
        "hist_by": hist_by,
        "bins_field": bins_field,
        "xmin_field": xmin_field,
        "xmax_field": xmax_field,
        "pdf_checkbox": pdf_checkbox,
        "cdf_checkbox": cdf_checkbox,
        "d32_checkbox": d32_checkbox,
        "mean_checkbox": mean_checkbox,
        "d23_checkbox": d23_checkbox,
        "prefix_field": prefix_field,
        "stats_area": stats_area,
        "summary_area": summary_area,
        "output_area": None,
        "log_area": log_area,
    })

    refresh_listener = CentralRefreshMaskOverlayListener(manual_state, state)
    refresh_manual_button.addActionListener(refresh_listener)
    add_current.addActionListener(CentralAddCurrentRoiListener(manual_state, state))
    add_manager.addActionListener(CentralAddRoiManagerListener(manual_state, state))

    root.add(tabs, BorderLayout.CENTER)
    buttons = JPanel()
    back_button = JButton("BACK")
    next_button = JButton("NEXT")
    ok_button = JButton("OK")
    change_model_button = JButton("CHANGE MODEL")
    finish_button = JButton("FINISH PROCESSING")
    cancel_button = JButton("CANCEL")
    back_button.addActionListener(CentralBackListener(state))
    next_button.addActionListener(CentralNextTabListener(state))
    ok_button.addActionListener(CentralOkListener(manual_state, state, frame))
    change_model_button.addActionListener(CentralChangeModelListener(manual_state, state, frame))
    finish_button.addActionListener(CentralFinishListener(manual_state, state, frame))
    cancel_button.addActionListener(CentralCancelListener(state, frame))
    buttons.add(back_button)
    buttons.add(next_button)
    buttons.add(ok_button)
    buttons.add(change_model_button)
    buttons.add(finish_button)
    buttons.add(cancel_button)
    root.add(buttons, BorderLayout.SOUTH)

    frame.getContentPane().add(root, BorderLayout.CENTER)
    frame.setSize(980, 720)
    try:
        frame.setLocation(1040, 80)
    except Exception:
        frame.setLocationRelativeTo(None)
    frame.setVisible(True)
    while not state["done"]:
        Thread.sleep(200)
    if state["action"] == "CANCEL":
        raise SystemExit
    if state["action"] == "CHANGE_MODEL":
        return "CHANGE_MODEL"
    return state.get("manual_count", 0)


def prompt_histogram_review(histogram_png, outputs, run_dir, manual_count):
    if histogram_png and File(histogram_png).isFile():
        IJ.open(histogram_png)
    source_csv = histogram_csv_for_review(outputs, run_dir, manual_count)
    if source_csv == "":
        return "NEXT"

    state = {"done": False, "action": "CANCEL", "run_dir": run_dir}
    frame = JFrame("BubMask Histogram Analysis")
    frame.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE)
    root = JPanel(BorderLayout())

    controls = JPanel(GridBagLayout())
    hist_by = JComboBox(["Count", "Fraction", "Probability density"])
    bins_field = JTextField("15", 8)
    xmin_field = JTextField("0.0", 8)
    xmax_field = JTextField("0.0", 8)
    pdf_checkbox = JCheckBox("PDF", False)
    cdf_checkbox = JCheckBox("CDF", False)
    d32_checkbox = JCheckBox("D32 / Sauter mean", True)
    mean_checkbox = JCheckBox("Mean diameter", True)
    d23_checkbox = JCheckBox("D23 marker", False)
    prefix_field = JTextField("histogram_analysis", 18)
    add_form_row(controls, 0, "Histogram by", hist_by)
    add_form_row(controls, 1, "Number of bins", bins_field)
    add_form_row(controls, 2, "X-axis minimum", xmin_field)
    add_form_row(controls, 3, "X-axis maximum", xmax_field)
    add_form_row(controls, 4, "Show PDF", pdf_checkbox)
    add_form_row(controls, 5, "Show CDF", cdf_checkbox)
    add_form_row(controls, 6, "Show D32", d32_checkbox)
    add_form_row(controls, 7, "Show mean", mean_checkbox)
    add_form_row(controls, 8, "Show D23", d23_checkbox)
    add_form_row(controls, 9, "Output prefix", prefix_field)

    table_model = create_analysis_table_model(source_csv)
    bubble_table = JTable(table_model)
    stats_area = JTextArea("Press NEXT/OK to regenerate graph and statistics.")
    stats_area.setEditable(False)
    stats_area.setFont(Font("Monospaced", Font.PLAIN, 12))
    tabs = JTabbedPane()
    tabs.addTab("Histogram Options", JScrollPane(controls))
    tabs.addTab("Bubble Table", JScrollPane(bubble_table))
    tabs.addTab("Statistics", JScrollPane(stats_area))
    root.add(tabs, BorderLayout.CENTER)

    message = JLabel("Edit bubble diameters/table values if needed, then press NEXT/OK.")
    root.add(message, BorderLayout.NORTH)
    buttons = JPanel()
    back_button = JButton("BACK")
    next_button = JButton("NEXT/OK")
    cancel_button = JButton("CANCEL")
    state.update({
        "hist_by": hist_by,
        "bins_field": bins_field,
        "xmin_field": xmin_field,
        "xmax_field": xmax_field,
        "pdf_checkbox": pdf_checkbox,
        "cdf_checkbox": cdf_checkbox,
        "d32_checkbox": d32_checkbox,
        "mean_checkbox": mean_checkbox,
        "d23_checkbox": d23_checkbox,
        "prefix_field": prefix_field,
        "table_model": table_model,
        "stats_area": stats_area,
        "message": message,
    })
    back_button.addActionListener(HistogramAnalysisButtonListener(state, frame, "BACK"))
    next_button.addActionListener(HistogramAnalysisButtonListener(state, frame, "NEXT"))
    cancel_button.addActionListener(HistogramAnalysisButtonListener(state, frame, "CANCEL"))
    buttons.add(back_button)
    buttons.add(next_button)
    buttons.add(cancel_button)
    root.add(buttons, BorderLayout.SOUTH)

    frame.getContentPane().add(root, BorderLayout.CENTER)
    frame.setSize(980, 680)
    frame.setLocationRelativeTo(None)
    frame.setVisible(True)
    while not state["done"]:
        Thread.sleep(200)
    if state["action"] == "CANCEL":
        raise SystemExit
    return state["action"]


def run_mask_and_histogram_review(imp, outputs, measurements, run_dir, pixel_width, pixel_height, unit, calibration_status, calibration_source, quality_gate_mode):
    manual_state = create_manual_review_state(
        imp,
        outputs,
        measurements,
        pixel_width,
        pixel_height,
        unit,
        calibration_status,
        calibration_source,
        quality_gate_mode,
    )
    return show_central_bubmask_review_window(manual_state, outputs, run_dir)


try:
    imp = IJ.getImage()
except Exception:
    IJ.showMessage("BubMask", "Please open an image before running BubMask.")
    raise

def reset_bubmask_display_state():
    del SUMMARY_ROWS[:]
    del OUTPUT_ROWS[:]
    del MEASUREMENT_ROWS[:]
    del LOG_LINES[:]


def run_bubmask_once(imp):
    global summary_rt
    global outputs_rt
    reset_bubmask_display_state()
    settings = show_bubmask_settings_window()
    if settings is None:
        raise SystemExit

    method_choice = settings["method_choice"]
    inference_mode = settings["inference_mode"]
    model_choice = settings["model_choice"]
    confidence = settings["confidence"]
    manual_px_per_mm = settings["manual_px_per_mm"]
    overlay_mode = settings["overlay_mode"]
    preprocessing_profile = settings["preprocessing_profile"]
    quality_gate_mode = settings["quality_gate_mode"]
    processing_preview_mode = settings["processing_preview_mode"]
    measure_sharp_only = settings["measure_sharp_only"]
    min_focus_score = settings["min_focus_score"]
    min_diameter_px = settings["min_diameter_px"]
    max_diameter_px = settings["max_diameter_px"]
    background_image_path = settings["background_image_path"]
    background_correction_mode = settings["background_correction_mode"]
    background_offset = settings["background_offset"]
    model_package = BUBMASK_MODEL_PATHS.get(model_choice, BUBMASK_MODEL)

    run_dir = create_run_dir(imp)

    image_path = ensure_image_file(imp, run_dir)
    request_path = File(run_dir, "request_from_fiji.json").getAbsolutePath()
    response_path = File(run_dir, "response_from_fiji.json").getAbsolutePath()

    cal = imp.getCalibration()
    unit = cal.getUnit() if cal is not None and cal.getUnit() is not None else "pixel"
    pixel_width = cal.pixelWidth if cal is not None else 1.0
    pixel_height = cal.pixelHeight if cal is not None else 1.0
    calibration_source = "missing"
    calibration_status = "missing"
    px_per_mm = 0.0
    unit_lower = unit.lower() if unit is not None else "pixel"
    if manual_px_per_mm > 0:
        pixel_width = 1.0 / manual_px_per_mm
        pixel_height = 1.0 / manual_px_per_mm
        unit = "mm"
        px_per_mm = manual_px_per_mm
        calibration_source = "manual_px_per_mm"
        calibration_status = "known"
    elif unit_lower not in ["pixel", "pixels", "px"] and pixel_width > 0 and pixel_height > 0:
        calibration_source = "fiji_imageplus"
        calibration_status = "known"
    else:
        pixel_width = 1.0
        pixel_height = 1.0
        unit = "pixel"

    request = """{
      "schema_version": "bubmask.request.v1",
      "source_title": "%s",
      "image_path": "%s",
      "model_package": "%s",
      "model_package_label": "%s",
      "inference_mode": "%s",
      "overlay_display": "%s",
      "preprocessing_profile": "%s",
      "quality_gate_mode": "%s",
      "processing_preview_display": "%s",
      "measure_sharp_bubbles_only": %s,
      "min_focus_score": %s,
      "min_diameter_px": %s,
      "max_diameter_px": %s,
      "calibration_status": "%s",
      "calibration_source": "%s",
      "px_per_mm": %s,
      "background_image_path": "%s",
      "background_correction_mode": "%s",
      "background_offset": %s,
      "run_output_dir": "%s",
      "width_px": %d,
      "height_px": %d,
      "n_slices": %d,
      "n_frames": %d,
      "pixel_width": %s,
      "pixel_height": %s,
      "unit": "%s",
      "confidence_threshold": %s
    }
    """ % (
        json_escape(imp.getTitle()),
        json_escape(image_path),
        json_escape(model_package),
        json_escape(model_choice),
        json_escape(inference_mode),
        json_escape(overlay_mode),
        json_escape(preprocessing_profile),
        json_escape(quality_gate_mode),
        json_escape(processing_preview_mode),
        "true" if measure_sharp_only else "false",
        min_focus_score,
        min_diameter_px,
        max_diameter_px,
        json_escape(calibration_status),
        json_escape(calibration_source),
        px_per_mm,
        json_escape(background_image_path),
        json_escape(background_correction_mode),
        background_offset,
        json_escape(run_dir.getAbsolutePath()),
        imp.getWidth(),
        imp.getHeight(),
        imp.getNSlices(),
        imp.getNFrames(),
        pixel_width,
        pixel_height,
        json_escape(unit),
        confidence,
    )
    write_text(request_path, request)

    log_message("BubMask worker request: " + request_path)
    log_message("BubMask worker response: " + response_path)
    exit_code, stdout, stderr = run_worker(request_path, response_path)
    stdout_path = File(run_dir, "worker_stdout.log").getAbsolutePath()
    stderr_path = File(run_dir, "worker_stderr.log").getAbsolutePath()
    write_text(stdout_path, stdout if stdout else "")
    write_text(stderr_path, stderr if stderr else "")
    if stdout:
        log_message("BubMask worker stdout:\n" + stdout)
    if stderr:
        log_message("BubMask worker stderr:\n" + stderr)

    summary_rt = ResultsTable()
    outputs_rt = ResultsTable()
    outputs = None
    worker_ok = False
    add_summary_row(summary_rt, "Input", "source image", imp.getTitle())
    add_summary_row(summary_rt, "Input", "width x height px", str(imp.getWidth()) + " x " + str(imp.getHeight()))
    add_summary_row(summary_rt, "Run", "output folder", run_dir.getAbsolutePath())
    add_summary_row(summary_rt, "Mode", "bubble detection method", method_choice)
    add_summary_row(summary_rt, "Mode", "inference", inference_mode)
    add_summary_row(summary_rt, "Mode", "model package", model_choice)
    add_summary_row(summary_rt, "Mode", "model path", model_package)
    add_summary_row(summary_rt, "Mode", "overlay display", overlay_mode)
    add_summary_row(summary_rt, "Mode", "preprocessing", preprocessing_profile)
    add_summary_row(summary_rt, "Mode", "quality gate", quality_gate_mode)
    add_summary_row(summary_rt, "Mode", "processing previews", processing_preview_mode)
    add_summary_row(summary_rt, "Quality", "measure sharp bubbles only", str(measure_sharp_only))
    add_summary_row(summary_rt, "Quality", "minimum focus score", min_focus_score)
    add_summary_row(summary_rt, "Quality", "minimum diameter px", min_diameter_px)
    add_summary_row(summary_rt, "Quality", "maximum diameter px", max_diameter_px)
    add_summary_row(summary_rt, "Calibration", "status", calibration_status)
    add_summary_row(summary_rt, "Calibration", "source", calibration_source)
    add_summary_row(summary_rt, "Calibration", "manual px/mm", manual_px_per_mm)
    add_summary_row(summary_rt, "Calibration", "pixel width", pixel_width)
    add_summary_row(summary_rt, "Calibration", "pixel height", pixel_height)
    add_summary_row(summary_rt, "Calibration", "unit", unit)
    add_summary_row(summary_rt, "Background", "image", background_image_path)
    add_summary_row(summary_rt, "Background", "correction", background_correction_mode)
    add_output_row(outputs_rt, "run folder", run_dir.getAbsolutePath())
    add_output_row(outputs_rt, "request JSON", request_path)
    add_output_row(outputs_rt, "response JSON", response_path)
    add_output_row(outputs_rt, "worker stdout log", stdout_path)
    add_output_row(outputs_rt, "worker stderr log", stderr_path)

    if File(response_path).isFile():
        text = open(response_path, "r").read()
        data = JSONObject(text)
        if data.optString("status") == "error":
            add_summary_row(summary_rt, "Run", "status", "worker_failed")
            if data.has("error"):
                error = data.getJSONObject("error")
                add_summary_row(summary_rt, "Error", "type", error.optString("type"))
                add_summary_row(summary_rt, "Error", "message", error.optString("message"))
                log_message("BubMask worker error:\n" + error.optString("traceback"))
        elif exit_code == 0:
            masks = data.getJSONArray("masks")
            measurements = data.getJSONArray("measurements")
            outputs = data.getJSONObject("outputs") if data.has("outputs") else None
            drawn_count, total_count = draw_detection_overlay(imp, data, inference_mode, overlay_mode)
            if imp.getWindow() is not None:
                imp.getWindow().toFront()
            worker_ok = True
            add_summary_row(summary_rt, "Run", "status", "worker_ok")
            add_summary_row(summary_rt, "Detection", "detections", masks.length())
            add_summary_row(summary_rt, "Detection", "measurements", measurements.length())
            add_summary_row(summary_rt, "Overlay", "drawn on active image", str(drawn_count) + " / " + str(total_count))
            if calibration_status != "known":
                log_message("BubMask calibration warning: Pixel size is missing. BubMask can report pixel units only. Physical diameter cannot be trusted until calibration is provided.")
                add_summary_row(summary_rt, "Warning", "calibration", "Pixel size is missing. Physical diameter cannot be trusted.")
            if data.has("diagnostics"):
                diagnostics = data.getJSONObject("diagnostics")
                if diagnostics.has("calibration"):
                    calibration = diagnostics.getJSONObject("calibration")
                    add_summary_row(summary_rt, "Worker calibration", "status", calibration.optString("status"))
                    add_summary_row(summary_rt, "Worker calibration", "source", calibration.optString("source"))
                    add_summary_row(summary_rt, "Worker calibration", "px/mm", calibration.optDouble("px_per_mm"))
                if diagnostics.has("quality_summary"):
                    add_summary_row(summary_rt, "Bubble summary", "bubbles", measurements.length())
            if data.has("outputs"):
                bubble_xlsx = File(run_dir, "bubble_measurements.xlsx").getAbsolutePath()
                excel_exit = run_excel_export_for_csv(outputs.optString("per_bubble_csv"), bubble_xlsx)
                if excel_exit == 0:
                    add_output_row(outputs_rt, "bubble list Excel", bubble_xlsx)
                else:
                    log_message("Excel bubble-list export failed with exit code " + str(excel_exit))
                add_output_row(outputs_rt, "per-bubble CSV", outputs.optString("per_bubble_csv"))
                add_output_row(outputs_rt, "box overlay PNG", outputs.optString("overlay_png"))
                add_output_row(outputs_rt, "box overlay TIFF", outputs.optString("overlay_tif"))
                add_output_row(outputs_rt, "mask overlay PNG", outputs.optString("overlay_masks_png"))
                add_output_row(outputs_rt, "mask overlay TIFF", outputs.optString("overlay_masks_tif"))
                add_output_row(outputs_rt, "instance labels TIFF", outputs.optString("instance_labels_tif"))
                add_output_row(outputs_rt, "background-corrected PNG", outputs.optString("background_corrected_png"))
                add_output_row(outputs_rt, "background-corrected TIFF", outputs.optString("background_corrected_tif"))
                add_output_row(outputs_rt, "preprocessed PNG", outputs.optString("preprocessed_png"))
                add_output_row(outputs_rt, "preprocessed TIFF", outputs.optString("preprocessed_tif"))
                add_output_row(outputs_rt, "processing preview PNG", outputs.optString("processing_preview_png"))
                add_output_row(outputs_rt, "FOV mask TIFF", outputs.optString("fov_mask_tif"))
                add_output_row(outputs_rt, "histogram all CSV", outputs.optString("diameter_histogram_all_csv"))
                add_output_row(outputs_rt, "histogram all PNG", outputs.optString("diameter_histogram_all_png"))
                add_output_row(outputs_rt, "accepted histogram CSV", outputs.optString("diameter_histogram_accepted_csv"))
                add_output_row(outputs_rt, "accepted histogram PNG", outputs.optString("diameter_histogram_accepted_png"))
                add_output_row(outputs_rt, "raw-vs-reconstructed histogram CSV", outputs.optString("diameter_histogram_raw_vs_reconstructed_csv"))
                add_output_row(outputs_rt, "raw-vs-reconstructed histogram PNG", outputs.optString("diameter_histogram_raw_vs_reconstructed_png"))
                add_output_row(outputs_rt, "histogram summary JSON", outputs.optString("diameter_histogram_summary_json"))
                add_output_row(outputs_rt, "summary JSON", outputs.optString("summary_json"))
            if measurements.length() > 0:
                bubble_rt, shown_count, full_count = compact_measurement_table(measurements, unit)
                if full_count > shown_count:
                    add_summary_row(summary_rt, "Bubble table", "shown", str(shown_count) + " of " + str(full_count))
            review_manual_count = run_mask_and_histogram_review(
                    imp,
                    outputs,
                    measurements,
                    run_dir,
                    pixel_width,
                    pixel_height,
                    unit,
                    calibration_status,
                    calibration_source,
                    quality_gate_mode,
            )
            if review_manual_count == "CHANGE_MODEL":
                add_summary_row(summary_rt, "Run", "status", "model_change_requested")
                return "CHANGE_MODEL"
            add_summary_row(summary_rt, "Manual bubbles", "final added count", review_manual_count)
        else:
            add_summary_row(summary_rt, "Run", "status", "worker_failed")
            add_summary_row(summary_rt, "Error", "message", "Worker wrote a response JSON but exited with code " + str(exit_code))
    else:
        add_summary_row(summary_rt, "Run", "status", "worker_failed")
        add_summary_row(summary_rt, "Error", "message", stderr)

    artifact_choices = collect_artifact_choices(run_dir, request_path, response_path, stdout_path, stderr_path, outputs)
    retention_status = apply_result_retention(run_dir, artifact_choices)
    add_summary_row(summary_rt, "Result files", "retention", retention_status)

    if worker_ok and outputs is not None and File(run_dir.getAbsolutePath()).isDirectory():
        add_summary_row(summary_rt, "Overlay", "preview location", "shown in BubMask Review and Analysis tabs")
        add_summary_row(summary_rt, "Processing", "preview location", "shown in BubMask Review and Analysis tabs")
    elif worker_ok:
        add_summary_row(summary_rt, "Overlay", "preview location", "result files were not kept")
        add_summary_row(summary_rt, "Processing", "preview location", "result files were not kept")

    show_tabbed_results()
    return "FINISH"


while True:
    bubmask_action = run_bubmask_once(imp)
    if bubmask_action == "CHANGE_MODEL":
        continue
    break
IJ.showStatus("BubMask completed")
