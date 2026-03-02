import os
import pickle
from read_lib import read_lib


def load_libs(LIB_CACHE_FILE):
    raw_libs = None
    if os.path.exists(LIB_CACHE_FILE):
        print(f"[INFO] Found cache file '{LIB_CACHE_FILE}', loading directly...")
        try:
            with open(LIB_CACHE_FILE, "rb") as f:
                raw_libs = pickle.load(f)
            print("[INFO] Libraries loaded from cache successfully.")
        except Exception as e:
            print(f"[WARN] Failed to load cache: {e}. Fallback to parsing.")
            raw_libs = None
    if raw_libs is None:
        print("[INFO] Parsing libraries from source (this may take a while)...")
        raw_libs = read_lib()

        if raw_libs:
            print(f"[INFO] Saving parsed libraries to cache '{LIB_CACHE_FILE}'...")
            try:
                with open(LIB_CACHE_FILE, "wb") as f:
                    pickle.dump(raw_libs, f)
            except Exception as e:
                print(f"[WARN] Could not save cache: {e}")

    return raw_libs
