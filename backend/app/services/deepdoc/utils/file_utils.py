import os


def get_project_base_directory(*args):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
    if args:
        return os.path.join(base_dir, *args)
    return base_dir


def traversal_files(base):
    for root, ds, fs in os.walk(base):
        for f in fs:
            fullname = os.path.join(root, f)
            yield fullname
