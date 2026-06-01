package edu.unsw.mining.bubmask;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.scijava.log.LogService;

/**
 * Small managed-process client for the BubMask Python worker.
 */
public class BubMaskWorkerClient {

	private final LogService log;

	public BubMaskWorkerClient(final LogService log) {
		this.log = log;
	}

	public WorkerResult run(final String pythonExecutable, final File workerScript,
		final String requestJson, final long timeoutMillis) throws Exception
	{
		final File requestFile = File.createTempFile("bubmask-request-", ".json");
		try {
			write(requestFile, requestJson);
			final List<String> command = new ArrayList<String>();
			command.add(pythonExecutable == null || pythonExecutable.trim().length() == 0 ?
				"python" : pythonExecutable);
			command.add(workerScript.getAbsolutePath());
			command.add("--input");
			command.add(requestFile.getAbsolutePath());

			final ProcessBuilder builder = new ProcessBuilder(command);
			builder.redirectErrorStream(true);
			final Process process = builder.start();
			final String output = readProcessOutput(process);
			final boolean completed = process.waitFor(timeoutMillis, TimeUnit.MILLISECONDS);
			if (!completed) {
				process.destroyForcibly();
				throw new IOException("Python worker timed out after " + timeoutMillis + " ms");
			}
			if (process.exitValue() != 0) {
				throw new IOException("Python worker exited with " + process.exitValue() +
					": " + output);
			}
			if (log != null) log.debug("BubMask worker response: " + output);
			return WorkerResult.parse(output);
		}
		finally {
			if (!requestFile.delete() && log != null) {
				log.debug("Could not delete temporary request file: " + requestFile);
			}
		}
	}

	private static void write(final File file, final String contents)
		throws IOException
	{
		final FileWriter writer = new FileWriter(file);
		try {
			writer.write(contents);
		}
		finally {
			writer.close();
		}
	}

	private static String readProcessOutput(final Process process)
		throws IOException
	{
		final BufferedReader reader = new BufferedReader(new InputStreamReader(
			process.getInputStream(), "UTF-8"));
		final StringBuilder sb = new StringBuilder();
		try {
			String line;
			while ((line = reader.readLine()) != null) {
				sb.append(line).append('\n');
			}
		}
		finally {
			reader.close();
		}
		return sb.toString();
	}

	public static class WorkerResult {

		public String modelName = "";
		public String modelHash = "";
		public int bubbleId = -1;
		public double score = Double.NaN;
		public double areaPx = Double.NaN;
		public double diameterEq = Double.NaN;
		public String diameterUnit = "";
		public double centroidX = Double.NaN;
		public double centroidY = Double.NaN;
		public String perBubbleCsv = "";
		public String overlayPng = "";
		public String overlayTif = "";
		public String summaryJson = "";

		public static WorkerResult parse(final String output) throws IOException {
			final String json = jsonObject(output);
			final WorkerResult result = new WorkerResult();
			result.modelName = stringValue(json, "name", "");
			result.modelHash = stringValue(json, "hash", "");
			result.bubbleId = (int) numberValue(json, "bubble_id", -1);
			result.score = numberValue(json, "score", Double.NaN);
			result.areaPx = numberValue(json, "area_px", Double.NaN);
			result.diameterEq = numberValue(json,
				"equivalent_diameter_calibrated", Double.NaN);
			if (Double.isNaN(result.diameterEq)) {
				result.diameterEq = numberValue(json, "diameter_eq_um", Double.NaN);
			}
			result.diameterUnit = stringValue(json, "diameter_unit", "");
			result.centroidX = numberValue(json, "centroid_x_px", Double.NaN);
			result.centroidY = numberValue(json, "centroid_y_px", Double.NaN);
			result.perBubbleCsv = stringValue(json, "per_bubble_csv", "");
			result.overlayPng = stringValue(json, "overlay_png", "");
			result.overlayTif = stringValue(json, "overlay_tif", "");
			result.summaryJson = stringValue(json, "summary_json", "");
			return result;
		}

		private static String jsonObject(final String output) throws IOException {
			final int start = output.indexOf('{');
			final int end = output.lastIndexOf('}');
			if (start < 0 || end <= start) {
				throw new IOException("Worker did not return a JSON object: " + output);
			}
			return output.substring(start, end + 1);
		}

		private static String stringValue(final String json, final String key,
			final String fallback)
		{
			final Pattern p = Pattern.compile("\"" + Pattern.quote(key) +
				"\"\\s*:\\s*\"([^\"]*)\"");
			final Matcher m = p.matcher(json);
			return m.find() ? m.group(1) : fallback;
		}

		private static double numberValue(final String json, final String key,
			final double fallback)
		{
			final Pattern p = Pattern.compile("\"" + Pattern.quote(key) +
				"\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)");
			final Matcher m = p.matcher(json);
			return m.find() ? Double.parseDouble(m.group(1)) : fallback;
		}
	}
}
