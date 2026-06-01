package edu.unsw.mining.bubmask;

import ij.ImagePlus;

/**
 * JSON request builder for the Python worker.
 *
 * <p>This class deliberately avoids a JSON dependency for the first integration
 * milestone. Replace it with Jackson/Gson or SciJava JSON utilities once the
 * schema stabilizes.</p>
 */
public final class WorkerJson {

	private WorkerJson() {
		// Utility class.
	}

	public static String request(final ImagePlus imp, final double pixelWidth,
		final double pixelHeight, final String unit, final double threshold)
	{
		return request(imp, pixelWidth, pixelHeight, unit, threshold, null, null);
	}

	public static String request(final ImagePlus imp, final double pixelWidth,
		final double pixelHeight, final String unit, final double threshold,
		final String imagePath, final String modelPackage)
	{
		return request(imp, pixelWidth, pixelHeight, unit, threshold, imagePath,
			modelPackage, "placeholder", null);
	}

	public static String request(final ImagePlus imp, final double pixelWidth,
		final double pixelHeight, final String unit, final double threshold,
		final String imagePath, final String modelPackage,
		final String inferenceMode, final String runOutputDir)
	{
		return request(imp, pixelWidth, pixelHeight, unit, threshold, imagePath,
			modelPackage, inferenceMode, runOutputDir, "raw_model", "review_only");
	}

	public static String request(final ImagePlus imp, final double pixelWidth,
		final double pixelHeight, final String unit, final double threshold,
		final String imagePath, final String modelPackage,
		final String inferenceMode, final String runOutputDir,
		final String preprocessingProfile, final String qualityGateMode)
	{
		return request(imp, pixelWidth, pixelHeight, unit, threshold, imagePath,
			modelPackage, inferenceMode, runOutputDir, preprocessingProfile,
			qualityGateMode, "missing", "pixel_units_only", 0.0, "", "none");
	}

	public static String request(final ImagePlus imp, final double pixelWidth,
		final double pixelHeight, final String unit, final double threshold,
		final String imagePath, final String modelPackage,
		final String inferenceMode, final String runOutputDir,
		final String preprocessingProfile, final String qualityGateMode,
		final String calibrationStatus, final String calibrationSource,
		final double pxPerMm, final String backgroundImagePath,
		final String backgroundCorrectionMode)
	{
		final StringBuilder sb = new StringBuilder();
		sb.append("{\n");
		field(sb, "schema_version", "bubmask.request.v1", true);
		field(sb, "source_title", imp.getTitle(), true);
		field(sb, "image_path", imagePath == null ? "" : imagePath, true);
		field(sb, "model_package", modelPackage == null ? "" : modelPackage, true);
		field(sb, "inference_mode", inferenceMode == null ? "placeholder" :
			inferenceMode, true);
		field(sb, "preprocessing_profile", preprocessingProfile == null ?
			"raw_model" : preprocessingProfile, true);
		field(sb, "quality_gate_mode", qualityGateMode == null ? "review_only" :
			qualityGateMode, true);
		field(sb, "calibration_status", calibrationStatus == null ? "missing" :
			calibrationStatus, true);
		field(sb, "calibration_source", calibrationSource == null ?
			"pixel_units_only" : calibrationSource, true);
		number(sb, "px_per_mm", pxPerMm, true);
		field(sb, "background_image_path", backgroundImagePath == null ? "" :
			backgroundImagePath, true);
		field(sb, "background_correction_mode", backgroundCorrectionMode == null ?
			"none" : backgroundCorrectionMode, true);
		field(sb, "run_output_dir", runOutputDir == null ? "" : runOutputDir, true);
		number(sb, "width_px", imp.getWidth(), true);
		number(sb, "height_px", imp.getHeight(), true);
		number(sb, "n_slices", imp.getNSlices(), true);
		number(sb, "n_frames", imp.getNFrames(), true);
		number(sb, "pixel_width", pixelWidth, true);
		number(sb, "pixel_height", pixelHeight, true);
		field(sb, "unit", unit, true);
		number(sb, "confidence_threshold", threshold, false);
		sb.append("}\n");
		return sb.toString();
	}

	private static void field(final StringBuilder sb, final String name,
		final String value, final boolean comma)
	{
		sb.append("  \"").append(name).append("\": \"")
			.append(escape(value)).append("\"");
		if (comma) sb.append(',');
		sb.append('\n');
	}

	private static void number(final StringBuilder sb, final String name,
		final double value, final boolean comma)
	{
		sb.append("  \"").append(name).append("\": ").append(value);
		if (comma) sb.append(',');
		sb.append('\n');
	}

	private static String escape(final String value) {
		if (value == null) return "";
		return value.replace("\\", "\\\\").replace("\"", "\\\"");
	}
}
