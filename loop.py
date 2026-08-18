import os
import subprocess
from multiprocessing import Pool
import sys

import cv2
def process_single_pdf(file_info):
    script_dir, file = file_info
    full_path = os.path.join(script_dir, file)

    base_name = file[:-4]  # Strip '.pdf'
    output_file = f"{base_name}_converted.pdf"
    output_path = os.path.join(script_dir, output_file)

    command = ['python', 'convert_pdf.py', full_path, output_path]
    print(f"Converting: {file} -> {output_file}")

    subprocess.run(command)

def convert_all_pdfs_parallel():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    files = os.listdir(script_dir)

    # Filter valid PDF files
    tasks = [
        (script_dir, file)
        for file in files
        if file.lower().endswith('.pdf')
        and not file.endswith('_converted.pdf')
        and os.path.isfile(os.path.join(script_dir, file))
    ]
    print(tasks)
    # Run across 4 parallel processes
    with Pool(processes=4) as pool:
        pool.map(process_single_pdf, tasks)

if __name__ == '__main__':
    convert_all_pdfs_parallel()