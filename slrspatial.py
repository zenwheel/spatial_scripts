#!/usr/bin/env python3
import os
import subprocess
import argparse
import re
import sys

def orientation_to_jpegtran_arg(orientation: int) -> list[str] | None:
	return {
		1: None,
		2: ['-flip', 'horizontal'],
		3: ['-rotate', '180'],
		4: ['-flip', 'vertical'],
		5: ['-transpose'],
		6: ['-rotate', '90'],
		7: ['-transverse'],
		8: ['-rotate', '270']
	}.get(orientation)

def natural_sort_key(s):
	"""
	Sort strings containing numbers naturally (e.g., DSC01, DSC02, DSC10 instead of DSC01, DSC10, DSC02)
	"""
	return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def run_command(command, description=None):
	"""
	Run a shell command and handle errors
	"""
	if description:
		print(f"{description}...")

	try:
		result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
		return result.stdout.strip()
	except subprocess.CalledProcessError as e:
		print(f"Error: {e}")
		print(f"Command output: {e.stdout}")
		print(f"Command error: {e.stderr}")
		return None

def process_images(folder1, folder2, spatial_params=None):
	"""
	Process images in two folders:
	1. Ensure both folders have the same number of images
	2. Bake rotation into images using jpegtran
	3. Copy EXIF data from folder1 to folder2
	4. Rename images in folder2 to match folder1
	5. Run spatialPhotoTool on matching image pairs
	"""
	# Ensure the folders exist
	if not os.path.isdir(folder1):
		print(f"Error: Folder '{folder1}' doesn't exist.")
		sys.exit(1)

	if not os.path.isdir(folder2):
		print(f"Error: Folder '{folder2}' doesn't exist.")
		sys.exit(1)

	# Get all image files in both folders
	image_extensions = ('.jpg', '.jpeg', '.JPG', '.JPEG')

	folder1_images = [f for f in os.listdir(folder1) if os.path.isfile(os.path.join(folder1, f))
					and f.lower().endswith(image_extensions)]
	folder2_images = [f for f in os.listdir(folder2) if os.path.isfile(os.path.join(folder2, f))
					and f.lower().endswith(image_extensions)]

	# Sort images naturally
	folder1_images.sort(key=natural_sort_key)
	folder2_images.sort(key=natural_sort_key)

	# Check if both folders have the same number of images
	if len(folder1_images) != len(folder2_images):
		print(f"Error: Folders have different number of images.")
		print(f"Folder '{folder1}': {len(folder1_images)} images")
		print(f"Folder '{folder2}': {len(folder2_images)} images")
		sys.exit(1)

	print(f"Found {len(folder1_images)} images in each folder.")

	print("\nStep 1: Matching images...")

	for i, (img1, img2) in enumerate(zip(folder1_images, folder2_images)):
		if img2 != img1:
			print(f'{i}: {folder2}/{img2} -> {img1}')
			os.rename(f'{folder2}/{img2}', f'{folder2}/{img1}')

	# reload image list
	folder2_images = [f for f in os.listdir(folder2) if os.path.isfile(os.path.join(folder2, f))
					and f.lower().endswith(image_extensions)]

	# rotate images based on embedded EXIF data, this allows us to copy EXIF data to
	# stereo images without overwriting rotation metadata and messing up rotation later
	# this uses jpegtran which does this step LOSSLESSLY
	print("\nStep 2: Rotating images...")

	for i, img1 in enumerate(folder1_images):
		get_rotation_cmd = ['exiftool', '-Orientation#', '-s', '-s', '-s', f'{folder1}/{img1}']
		transform = orientation_to_jpegtran_arg(int(run_command(get_rotation_cmd)))
		if transform:
			print(f'{i}: Rotating: {img1}')
			jpeg_transform_cmd = ['jpegtran', '-copy', 'all', transform, '-outfile', 'rotated.jpg',  f'{folder1}/{img1}']
			jpeg_transform_cmd = [elem for item in jpeg_transform_cmd for elem in (item if isinstance(item, list) else [item])]
			run_command(jpeg_transform_cmd)
			# remove orientation flag if we rotated the image
			reset_exif_cmd = ['exiftool', '-Orientation=1', '-n', '-overwrite_original', 'rotated.jpg']
			run_command(reset_exif_cmd)
			os.rename('rotated.jpg', f'{folder1}/{img1}')
	for i, img2 in enumerate(folder2_images):
		get_rotation_cmd = ['exiftool', '-Orientation#', '-s', '-s', '-s', f'{folder2}/{img2}']
		transform = orientation_to_jpegtran_arg(int(run_command(get_rotation_cmd)))
		if transform:
			print(f'{i}: Rotating: {img2}')
			jpeg_transform_cmd = ['jpegtran', '-copy', 'all', transform, '-outfile', 'rotated.jpg',  f'{folder2}/{img2}']
			jpeg_transform_cmd = [elem for item in jpeg_transform_cmd for elem in (item if isinstance(item, list) else [item])]
			run_command(jpeg_transform_cmd)
			# remove orientation flag if we rotated the image
			reset_exif_cmd = ['exiftool', '-Orientation=1', '-n', '-overwrite_original', 'rotated.jpg']
			run_command(reset_exif_cmd)
			os.rename('rotated.jpg', f'{folder2}/{img2}')

	# align the images, this is important unless the cameras are perfectly aligned!
	# this stores the output as a TIFF to avoid generation loss at the cost of a
	# large temporary file
	print("\nStep 3: Align images...")

	for i, img_name in enumerate(folder1_images):
		img1_path = os.path.join(folder1, img_name)
		img2_path = os.path.join(folder2, img_name)

		name, _ = os.path.splitext(img_name)
		output_file = os.path.join(folder1, name + '-sbs.tiff')
		align_cmd = [
			"StereoAutoAlign",
			img1_path,
			img2_path,
			'10',
			output_file
		]
		run_command(align_cmd)

	# this step copies the EXIF data from the original LEFT side
	# images to the TIFF files, to preserve timestamps and camera
	# metadata, but give precedence to the LEFT camera, without doing
	# it at this point, the alignment step removes the metadata
	print("\nStep 4: Copy EXIF data to output images...")
	for i, img_name in enumerate(folder1_images):
		img1_path = os.path.join(folder1, img_name)
		name, _ = os.path.splitext(img_name)
		output_file = os.path.join(folder1, name + '-sbs.tiff')
		exiftool_cmd = [
			"exiftool",
			"-overwrite_original",
			"-TagsFromFile",
			img1_path,
			"-all:all",
			output_file
		]
		run_command(exiftool_cmd)

	# convert the TIFF file to a spatial image in a HEIF container
	# compatible with Apple devices
	if spatial_params:
		print("\nStep 5: Running spatialPhotoTool on matching image pairs...")

		for i, img_name in enumerate(folder1_images):
			img1_path = os.path.join(folder1, img_name)
			name, _ = os.path.splitext(img_name)
			output_file = os.path.join(folder1, name + '-sbs.tiff')

			# Build the spatialPhotoTool command
			spatial_cmd = [
				"spatialPhotoTool",
				"-s", str(spatial_params["s"]),
				"-f", str(spatial_params["f"]),
				"-b", str(spatial_params["b"]),
				output_file
			]
			run_command(spatial_cmd)

			if (i + 1) % 5 == 0 or i + 1 == len(folder1_images):
				print(f"  Processed {i + 1}/{len(folder1_images)} image pairs")

	print("\nAll processing steps completed successfully!")

def main():
	# Set up command-line argument parsing
	parser = argparse.ArgumentParser(
		description='Process and pair images from two folders for spatial photo creation.'
	)
	parser.add_argument('folder1', help='Path to the first folder of images')
	parser.add_argument('folder2', help='Path to the second folder of images')
	parser.add_argument('-s', type=float, default=23.5, help='Sensor size value for spatial image (default: 23.5)')
	parser.add_argument('-f', type=int, default=23, help='Focal length of lens value for spatial image (default: 23)')
	parser.add_argument('-b', type=float, default=105.0, help='Baseline/IPD parameter for spatial image (default: 105.0)')
	parser.add_argument('--skip-spatial', action='store_true', help='Skip conversion to spatial image')

	# Parse arguments
	args = parser.parse_args()

	# Set up spatial parameters
	spatial_params = None
	if not args.skip_spatial:
		spatial_params = {
			"s": args.s,
			"f": args.f,
			"b": args.b
		}

	process_images(args.folder1, args.folder2, spatial_params)

if __name__ == "__main__":
	main()
