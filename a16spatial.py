#!/usr/bin/env python3
import os
import re
import subprocess
import pathlib
import shutil
import argparse
from datetime import datetime

def apply_lens_correction(input_dir='files', lens_params="k1=-0.2:k2=-0.025"):
	"""
	Apply lens correction to all files in the specified directory using FFmpeg.

	Args:
		input_dir (str): Directory containing files to process
		lens_params (str): Lens correction parameters for FFmpeg
	"""
	# Ensure input directory exists
	if not os.path.isdir(input_dir):
		print(f"Error: Directory '{input_dir}' not found.")
		return

	# Create full path to input directory
	input_dir_path = os.path.join(os.getcwd(), input_dir)

	# Get list of all files in the directory
	files = [f for f in os.listdir(input_dir_path) if os.path.isfile(os.path.join(input_dir_path, f))]

	if not files:
		print(f"No files found in '{input_dir}'.")
		return

	print(f"Found {len(files)} files in '{input_dir}'.")

	# Process each file
	for i, filename in enumerate(files, 1):
		input_file = os.path.join(input_dir_path, filename)

		# Generate output filename with "-corrected" suffix
		file_path = pathlib.Path(filename)
		output_filename = f"{file_path.stem}-corrected{file_path.suffix}"
		output_file = os.path.join(input_dir_path, output_filename)

		# Build FFmpeg command
		ffmpeg_cmd = [
			"ffmpeg",
			"-i", input_file,
			"-vf", f"lenscorrection={lens_params}",
			"-q:v", "2",
			"-y",  # Overwrite output file if it exists
			output_file
		]

		print(f"[{i}/{len(files)}] Processing: {filename} -> {output_filename}")

		try:
			# Run FFmpeg command
			subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
			print(f"Successfully processed {filename}")
		except subprocess.CalledProcessError as e:
			print(f"Error processing {filename}: {e}")
			print(f"FFmpeg output: {e.stderr.decode()}")
		except Exception as e:
			print(f"Unexpected error processing {filename}: {e}")

def copy_exif_tags(source_dir='a', dest_dir=None):
	"""
	Copy exif tags from original files to their corresponding -corrected files.

	For each file 'filename.ext' in the source directory, find the corresponding
	'filename-sbs.tiff' file and copy all exif tags from the original to the corrected file.

	Args:
		source_dir (str): Directory containing original files
		dest_dir (str, optional): Directory containing corrected files. If None, uses source_dir.
	"""
	# Ensure source directory exists
	if not os.path.isdir(source_dir):
		print(f"Error: Source directory '{source_dir}' not found.")
		return

	# If destination directory not specified, use the same as source
	if dest_dir is None:
		dest_dir = source_dir
	elif not os.path.isdir(dest_dir):
		print(f"Error: Destination directory '{dest_dir}' not found.")
		return

	# Get absolute paths
	source_dir_path = os.path.abspath(source_dir)
	dest_dir_path = os.path.abspath(dest_dir)

	# Get all files in source directory
	source_files = [f for f in os.listdir(source_dir_path) if os.path.isfile(os.path.join(source_dir_path, f))]

	if not source_files:
		print(f"No files found in source directory '{source_dir}'.")
		return

	# Process files
	success_count = 0
	skipped_count = 0
	error_count = 0

	for source_file in source_files:
		# Get the base name and extension
		base_name, extension = os.path.splitext(source_file)

		# Skip files that already have -corrected in their name
		if base_name.endswith('-corrected') or base_name.endswith('-sbs'):
			print(f"Skipping {source_file} - already a corrected file.")
			skipped_count += 1
			continue

		# Generate the corrected filename
		corrected_file = f"{base_name}-sbs.tiff"
		corrected_path = os.path.join(dest_dir_path, corrected_file)

		# Check if the corrected file exists
		if not os.path.exists(corrected_path):
			print(f"Skipping {source_file} - corresponding corrected file not found: {corrected_file}")
			skipped_count += 1
			continue

		source_path = os.path.join(source_dir_path, source_file)

		# Build exiftool command
		command = [
			"exiftool",
			"-overwrite_original",  # Don't create backup files
			"-TagsFromFile",
			source_path,
			"-all:all>all:all",            # Copy all tags
			corrected_path
		]

		print(f"Processing: {source_file} → {corrected_file}")

		try:
			# Run exiftool command
			result = subprocess.run(command, check=True, capture_output=True, text=True)
			print(f"Successfully copied tags from {source_file} to {corrected_file}")
			if result.stdout:
				print(f"  Output: {result.stdout.strip()}")
			success_count += 1
		except subprocess.CalledProcessError as e:
			print(f"Error copying tags from {source_file} to {corrected_file}:")
			if e.stdout:
				print(f"  Output: {e.stdout.strip()}")
			if e.stderr:
				print(f"  Error: {e.stderr.strip()}")
			error_count += 1
		except Exception as e:
			print(f"Unexpected error processing {source_file}: {e}")
			error_count += 1

	print("\nTag copying summary:")
	print(f"Total source files: {len(source_files)}")
	print(f"Successfully processed: {success_count}")
	print(f"Skipped: {skipped_count}")
	print(f"Errors: {error_count}")

def set_datetime_from_filename(directory='a', pattern=r'IMG(\d{8})-(\d{6})'):
	"""
	Set EXIF date/time tags based on dates embedded in filenames.

	The script looks for filenames matching the pattern and extracts date and time information
	to set the following EXIF tags: DateTimeOriginal, CreateDate, and ModifyDate.

	Args:
		directory (str): Directory containing the image files
		pattern (str): Regular expression pattern to extract date and time from filenames
		dry_run (bool): If True, only show what would be done without making changes
	"""
	# Ensure directory exists
	if not os.path.isdir(directory):
		print(f"Error: Directory '{directory}' not found.")
		return

	# Get absolute path
	dir_path = os.path.abspath(directory)

	# Compile the regex pattern
	regex = re.compile(pattern)

	# Get all files in the directory
	files = [f for f in os.listdir(dir_path)
			if os.path.isfile(os.path.join(dir_path, f))
			and (f.lower().endswith('-sbs.tiff'))]

	if not files:
		print(f"No files found in directory '{directory}'.")
		return

	# Process files
	success_count = 0
	skipped_count = 0
	error_count = 0

	for filename in files:
		# Try to match the pattern
		match = regex.search(filename)
		if not match:
			print(f"Skipping {filename} - does not match the expected pattern.")
			skipped_count += 1
			continue

		# Extract date and time parts
		try:
			date_part = match.group(1)  # YYYYMMDD
			time_part = match.group(2)  # HHMMSS

			# Parse date and time
			year = date_part[0:4]
			month = date_part[4:6]
			day = date_part[6:8]

			hour = time_part[0:2]
			minute = time_part[2:4]
			second = time_part[4:6]

			# Format for exiftool: "YYYY:MM:DD HH:MM:SS"
			exif_datetime = f"{year}:{month}:{day} {hour}:{minute}:{second}"

			# Validate the date and time
			datetime.strptime(exif_datetime, "%Y:%m:%d %H:%M:%S")

			file_path = os.path.join(dir_path, filename)

			print(f"Processing: {filename}")
			print(f"  Extracted datetime: {exif_datetime}")

			# Build exiftool command to set multiple date/time tags
			command = [
				"exiftool",
				"-overwrite_original",
				"-DateTimeOriginal=" + exif_datetime,
				"-CreateDate=" + exif_datetime,
				"-ModifyDate=" + exif_datetime,
				file_path
			]

			# Run exiftool command
			result = subprocess.run(command, check=True, capture_output=True, text=True)
			print(f"  Successfully set date/time for {filename}")
			if result.stdout:
				print(f"  Output: {result.stdout.strip()}")
			success_count += 1

		except ValueError as e:
			print(f"Error parsing date/time from {filename}: {e}")
			error_count += 1
		except subprocess.CalledProcessError as e:
			print(f"Error setting date/time for {filename}:")
			if e.stdout:
				print(f"  Output: {e.stdout.strip()}")
			if e.stderr:
				print(f"  Error: {e.stderr.strip()}")
			error_count += 1
		except Exception as e:
			print(f"Unexpected error processing {filename}: {e}")
			error_count += 1

	print("\nDate/time setting summary:")
	print(f"Total files: {len(files)}")
	print(f"Successfully processed: {success_count}")
	print(f"Skipped (no match): {skipped_count}")
	print(f"Errors: {error_count}")

def match_and_rename_files(dir_a='a', dir_b='b'):
	"""
	Match files between two directories based on their number identifier and
	rename files in directory B to use the same prefix as their counterparts in directory A.

	Files are expected to follow the pattern 'prefix-number.extension'.

	Args:
		dir_a (str): Path to the source directory containing reference files
		dir_b (str): Path to the directory containing files to be renamed
	"""
	# Ensure both directories exist
	if not os.path.isdir(dir_a):
		print(f"Error: Directory '{dir_a}' not found.")
		return

	if not os.path.isdir(dir_b):
		print(f"Error: Directory '{dir_b}' not found.")
		return

	# Get full paths to directories
	dir_a_path = os.path.abspath(dir_a)
	dir_b_path = os.path.abspath(dir_b)

	# Dictionary to store files in directory A by their number identifier
	files_a = {}

	# Regular expression to extract prefix, number, and extension
	pattern = re.compile(r'(.+)-(\d+)-corrected\.(.+)')

	# Process files in directory A
	print(f"Scanning directory '{dir_a}'...")
	for filename in os.listdir(dir_a_path):
		if os.path.isfile(os.path.join(dir_a_path, filename)):
			match = pattern.match(filename)
			if match:
				prefix_a, number, extension = match.groups()
				files_a[number] = {
					'filename': filename,
					'prefix': prefix_a,
					'extension': extension
				}

	if not files_a:
		print(f"No matching files found in directory '{dir_a}'.")
		return

	print(f"Found {len(files_a)} matching files in directory '{dir_a}'.")

	# Process and rename files in directory B
	print(f"\nScanning directory '{dir_b}'...")
	renamed_count = 0
	skipped_count = 0
	errors_count = 0

	for filename in os.listdir(dir_b_path):
		file_path = os.path.join(dir_b_path, filename)
		if os.path.isfile(file_path):
			match = pattern.match(filename)
			if match:
				prefix_b, number, extension = match.groups()

				# Check if there's a matching file in directory A
				if number in files_a:
					# Get the prefix from directory A
					new_prefix = files_a[number]['prefix']

					# Skip if the prefixes are already the same
					if prefix_b == new_prefix:
						print(f"Skipping {filename} - prefix already matches.")
						skipped_count += 1
						continue

					# Create new filename
					new_filename = f"{new_prefix}-{number}-corrected.{extension}"
					new_file_path = os.path.join(dir_b_path, new_filename)

					# Rename the file
					try:
						shutil.move(file_path, new_file_path)
						print(f"Renamed: {filename} -> {new_filename}")
						renamed_count += 1
					except Exception as e:
						print(f"Error renaming {filename}: {e}")
						errors_count += 1
				else:
					print(f"No match found in directory '{dir_a}' for number {number} ({filename}).")
			else:
				print(f"Skipping {filename} - doesn't match expected pattern 'prefix-number.extension'.")

	print("\nSummary:")
	print(f"Total files in directory '{dir_a}': {len(files_a)}")
	print(f"Files renamed: {renamed_count}")
	print(f"Files skipped (already matching): {skipped_count}")
	print(f"Errors: {errors_count}")

def align_stereo_files(dir_a='a', dir_b='b'):
	"""
	Find matching files for stereo pairs in directories 'a' and 'b' and process them
	with StereoAutoAlign.

	Args:
		dir_a (str): Path to the first directory
		dir_b (str): Path to the second directory
	"""
	# Ensure both directories exist
	if not os.path.isdir(dir_a):
		print(f"Error: Directory '{dir_a}' not found.")
		return

	if not os.path.isdir(dir_b):
		print(f"Error: Directory '{dir_b}' not found.")
		return

	# Get full paths to directories
	dir_a_path = os.path.abspath(dir_a)
	dir_b_path = os.path.abspath(dir_b)

	# Get list of filenames in both directories
	files_a = {f for f in os.listdir(dir_a_path) if os.path.isfile(os.path.join(dir_a_path, f))}
	files_b = {f for f in os.listdir(dir_b_path) if os.path.isfile(os.path.join(dir_b_path, f))}

	# Find matching filenames
	matching_files = set()
	for file in files_a.intersection(files_b):
		# Check if the file has '-corrected' in the name (but before the extension)
		name, _ = os.path.splitext(file)
		if name.endswith('-corrected'):
			matching_files.add(file)

	if not matching_files:
		print("No matching filenames found between the two directories.")
		return

	print(f"Found {len(matching_files)} matching files in both directories.")

	# Process each matching file
	success_count = 0
	error_count = 0

	for i, filename in enumerate(sorted(matching_files), 1):
		file_a = os.path.join(dir_a_path, filename)
		file_b = os.path.join(dir_b_path, filename)

		name, _ = os.path.splitext(filename)
		name = name.replace('-corrected', '-sbs')
		output_file = os.path.join(dir_a_path, name + '.tiff')

		# Build command
		command = [
			"StereoAutoAlign",
			file_a, file_b,
			"10",
			output_file
		]

		print(f"\n[{i}/{len(matching_files)}] Processing: {filename}")
		print(f"Command: {' '.join(command)}")

		try:
			# Run the command
			result = subprocess.run(command, check=True, capture_output=True, text=True)
			print(f"Successfully processed {filename}")
			if result.stdout:
				print("Output:", result.stdout)
			success_count += 1
		except subprocess.CalledProcessError as e:
			print(f"Error processing {filename}: {e}")
			if e.stdout:
				print("Output:", e.stdout)
			if e.stderr:
				print("Error:", e.stderr)
			error_count += 1
		except Exception as e:
			print(f"Unexpected error processing {filename}: {e}")
			error_count += 1

	print("\nProcessing summary:")
	print(f"Total matching files: {len(matching_files)}")
	print(f"Successfully processed: {success_count}")
	print(f"Errors: {error_count}")

def process_stereo_files(dir='a', baseline=73, hfov=170):
	"""
	Find stereo images and processes them with spatialPhotoTool.

	Args:
		dir (str): Path to the directory to search
		baseline (int): The baseline parameter for spatialPhotoTool (-b)
		hfov (int): The horizontal field of view parameter for spatialPhotoTool (--hfov)
	"""
	# Ensure both directories exist
	if not os.path.isdir(dir):
		print(f"Error: Directory '{dir}' not found.")
		return

	# Get full paths to directories
	dir_path = os.path.abspath(dir)

	# Get list of filenames in both directories
	files = {f for f in os.listdir(dir_path) if os.path.isfile(os.path.join(dir_path, f))}

	# Find matching filenames
	matching_files = set()
	for file in files:
		# Check if the file has '-sbs' in the name (but before the extension)
		name, _ = os.path.splitext(file)
		if name.endswith('-sbs'):
			matching_files.add(file)

	if not matching_files:
		print("No stereo filenames found.")
		return

	print(f"Found {len(matching_files)} stereo files.")
	print(f"Using parameters: baseline={baseline}, hfov={hfov}")

	# Process each matching file
	success_count = 0
	error_count = 0

	for i, filename in enumerate(sorted(matching_files), 1):
		file = os.path.join(dir_path, filename)

		# Build command
		command = [
			"spatialPhotoTool",
			"-b", str(baseline),
			"--hfov", str(hfov),
			file
		]

		print(f"\n[{i}/{len(matching_files)}] Processing: {filename}")
		print(f"Command: {' '.join(command)}")

		try:
			# Run the command
			result = subprocess.run(command, check=True, capture_output=True, text=True)
			print(f"Successfully processed {filename}")
			if result.stdout:
				print("Output:", result.stdout)
			success_count += 1
		except subprocess.CalledProcessError as e:
			print(f"Error processing {filename}: {e}")
			if e.stdout:
				print("Output:", e.stdout)
			if e.stderr:
				print("Error:", e.stderr)
			error_count += 1
		except Exception as e:
			print(f"Unexpected error processing {filename}: {e}")
			error_count += 1

	print("\nProcessing summary:")
	print(f"Total matching files: {len(matching_files)}")
	print(f"Successfully processed: {success_count}")
	print(f"Errors: {error_count}")

def move_heic_files(dir_a='a'):
	"""
	Move all .heic files from the specified directory to the current directory.

	Args:
		dir_a (str): Path to the directory containing .heic files
	"""
	# Ensure directory exists
	if not os.path.isdir(dir_a):
		print(f"Error: Directory '{dir_a}' not found.")
		return

	# Get full paths
	dir_a_path = os.path.abspath(dir_a)
	current_dir = os.getcwd()

	# Find all .heic files (case insensitive)
	heic_files = []
	for filename in os.listdir(dir_a_path):
		if os.path.isfile(os.path.join(dir_a_path, filename)) and filename.lower().endswith('.heic'):
			heic_files.append(filename)

	if not heic_files:
		print(f"No .heic files found in '{dir_a}'.")
		return

	print(f"\nMoving {len(heic_files)} .heic files from '{dir_a}' to the current directory...")

	# Move each file
	success_count = 0
	error_count = 0

	for filename in heic_files:
		source_path = os.path.join(dir_a_path, filename)
		dest_path = os.path.join(current_dir, filename)

		# Check if file already exists in destination
		if os.path.exists(dest_path):
			print(f"Skipping {filename} - already exists in current directory.")
			continue

		try:
			import shutil
			shutil.move(source_path, dest_path)
			print(f"Moved: {filename}")
			success_count += 1
		except Exception as e:
			print(f"Error moving {filename}: {e}")
			error_count += 1

	print(f"\nFile moving summary:")
	print(f"Total .heic files: {len(heic_files)}")
	print(f"Successfully moved: {success_count}")
	print(f"Errors: {error_count}")

def main():
	# Set up command-line argument parsing
	parser = argparse.ArgumentParser(
		description='Process synchronized (via remote) camera photos from two cheap Action Cameras such as the Onlincam or Timnut 4k cameras via a pipeline to correct for lens distortion, alignment errors and then convert to Vision Pro compatible spatial photos with spatialPhotoTool.'
	)
	parser.add_argument('--right', '-r', type=str, default='right',
						help='Right Folder (default: ./right)')
	parser.add_argument('--left', '-l', type=str, default='left',
						help='Left Folder (default: ./left)')
	parser.add_argument('--baseline', '-b', type=int, default=73,
						help='Baseline (mm) (default: 73)')
	parser.add_argument('--hfov', '-f', type=int, default=170,
						help='Horizontal Field of View (Degrees) (default: 170)')
	# Parse arguments
	args = parser.parse_args()

	if not os.path.isdir(args.left):
		print(f"Error: Directory '{args.left}' not found.")
		return
	if not os.path.isdir(args.right):
		print(f"Error: Directory '{args.right}' not found.")
		return

	print("Starting lens correction processing...")
	apply_lens_correction(input_dir=args.left)
	apply_lens_correction(input_dir=args.right)
	print("Processing complete.")

	print("Fixing file names...")
	match_and_rename_files(dir_a=args.left, dir_b=args.right)
	print("Processing complete.")

	print("Starting stereo photo processing...")
	align_stereo_files(args.left, args.right)
	print("Processing complete.")

	print("Restoring EXIF tags...")
	copy_exif_tags(args.left)
	print("Processing complete.")

	print("Starting EXIF date/time setting process...")
	set_datetime_from_filename(args.left, r'IMG(\d{8})-(\d{6})')
	print("Process complete.")

	print("Starting spatial photo creation...")
	process_stereo_files(args.left, args.baseline, args.hfov)
	print("Processing complete.")

	move_heic_files(args.left)

if __name__ == "__main__":
	main()