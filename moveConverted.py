from pathlib import Path

def move_converted_files():
    current_dir = Path.cwd()
    target_dir = current_dir / "converted"

    target_dir.mkdir(exist_ok=True)

    for file_path in current_dir.glob("*_converted*"):
        if file_path.is_file():
            destination = target_dir / file_path.name
            file_path.rename(destination)
            print(f"Moved: {file_path.name} -> {target_dir.name}/")


# if __name__ == "__main__":
#     move_converted_files()