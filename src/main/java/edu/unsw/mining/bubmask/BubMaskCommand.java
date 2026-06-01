package edu.unsw.mining.bubmask;

import ij.ImagePlus;
import ij.WindowManager;
import ij.measure.Calibration;
import ij.measure.ResultsTable;

import java.io.File;

import org.scijava.command.Command;
import org.scijava.log.LogService;
import org.scijava.plugin.Parameter;
import org.scijava.plugin.Plugin;

/**
 * Minimal Fiji command proving the ImageJ integration path for BubMask.
 */
@Plugin(type = Command.class, menuPath = "Plugins>UNSW>BubMask Microbubble Sizing")
public class BubMaskCommand implements Command {

	@Parameter(required = false)
	private ImagePlus image;

	@Parameter
	private LogService log;

	@Parameter(label = "Run Python worker")
	private boolean runPythonWorker = true;

	@Parameter(label = "Python executable", required = false)
	private String pythonExecutable = "python";

	@Parameter(label = "Worker script", required = false, style = "file")
	private File workerScript;

	@Parameter(label = "Confidence threshold")
	private double confidenceThreshold = 0.50;

	@Parameter(label = "Timeout (seconds)")
	private int timeoutSeconds = 30;

	@Override
	public void run() {
		final ImagePlus imp = image == null ? WindowManager.getCurrentImage() : image;
		if (imp == null) {
			throw new IllegalArgumentException("BubMask needs an active ImagePlus.");
		}

		final Calibration cal = imp.getCalibration();
		final String unit = cal == null || cal.getUnit() == null ? "pixel" : cal.getUnit();
		final double pixelWidth = cal == null ? 1.0 : cal.pixelWidth;
		final double pixelHeight = cal == null ? 1.0 : cal.pixelHeight;

		log.info("BubMask input: title=" + imp.getTitle() +
			", width=" + imp.getWidth() +
			", height=" + imp.getHeight() +
			", slices=" + imp.getNSlices() +
			", frames=" + imp.getNFrames());
		log.info("BubMask calibration: pixelWidth=" + pixelWidth +
			", pixelHeight=" + pixelHeight + ", unit=" + unit);

		final ResultsTable table = ResultsTable.getResultsTable();
		table.incrementCounter();
		table.addValue("source", imp.getTitle());
		table.addValue("schema_version", "bubmask.results.v1");
		table.addValue("pixel_width", pixelWidth);
		table.addValue("pixel_height", pixelHeight);
		table.addValue("unit", unit);
		table.addValue("image_width_px", imp.getWidth());
		table.addValue("image_height_px", imp.getHeight());
		table.addValue("status", "java_command_ok");

		if (runPythonWorker) {
			runWorker(imp, pixelWidth, pixelHeight, unit, table);
		}
		else {
			table.addValue("worker_status", "skipped");
		}

		table.show("BubMask Results");
	}

	private void runWorker(final ImagePlus imp, final double pixelWidth,
		final double pixelHeight, final String unit, final ResultsTable table)
	{
		final File script = resolveWorkerScript();
		if (script == null || !script.isFile()) {
			final String path = script == null ? "<unset>" : script.getAbsolutePath();
			log.warn("BubMask Python worker not found: " + path);
			table.addValue("worker_status", "missing_worker");
			return;
		}

		final String request = WorkerJson.request(imp, pixelWidth, pixelHeight, unit,
			confidenceThreshold);
		try {
			final BubMaskWorkerClient.WorkerResult result =
				new BubMaskWorkerClient(log).run(pythonExecutable, script, request,
					timeoutSeconds * 1000L);
			table.addValue("worker_status", "ok");
			table.addValue("model_name", result.modelName);
			table.addValue("model_hash", result.modelHash);
			table.addValue("bubble_id", result.bubbleId);
			table.addValue("score", result.score);
			table.addValue("area_px", result.areaPx);
			table.addValue("diameter_eq_" + unit, result.diameterEq);
			table.addValue("centroid_x_px", result.centroidX);
			table.addValue("centroid_y_px", result.centroidY);
		}
		catch (final Exception exc) {
			log.error("BubMask Python worker failed", exc);
			table.addValue("worker_status", "failed");
			table.addValue("worker_error", exc.getMessage());
		}
	}

	private File resolveWorkerScript() {
		if (workerScript != null && workerScript.getPath() != null &&
			workerScript.getPath().trim().length() > 0)
		{
			return workerScript;
		}
		final String configured = System.getProperty("bubmask.worker");
		if (configured != null && configured.trim().length() > 0) {
			return new File(configured);
		}
		return new File("src/main/python/bubmask_worker.py");
	}
}
