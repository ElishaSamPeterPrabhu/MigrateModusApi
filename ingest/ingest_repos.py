import os
from git import Repo, GitCommandError
from pathlib import Path


def clone_or_pull_repo(repo_url, dest_dir):
    repo_name = os.path.basename(repo_url)
    repo_path = Path(dest_dir) / repo_name
    repo = None
    if repo_path.exists():
        print(f"Repository {repo_name} already exists. Pulling latest changes...")
        try:
            repo = Repo(repo_path)
            origin = repo.remotes.origin
            origin.pull()
            print(f"Pulled latest changes for {repo_name}.")
        except GitCommandError as e:
            print(f"Error pulling {repo_name}: {e}. Continuing with local version.")
        except Exception as e:
            print(f"An unexpected error occurred during pull for {repo_name}: {e}")
    else:
        print(f"Cloning {repo_url} to {repo_path}")
        try:
            repo = Repo.clone_from(repo_url, repo_path)
        except GitCommandError as e:
            print(f"Error cloning repository {repo_url}: {e}")
            raise
    return repo_path


def ingest_repos(v1_url, v2_url, dest_dir="repos"):
    os.makedirs(dest_dir, exist_ok=True)
    v1_path = clone_or_pull_repo(v1_url, dest_dir)
    v2_path = clone_or_pull_repo(v2_url, dest_dir)
    print("Repos ensured up-to-date (or cloned). Ready for analysis.")
    print(f"V1: {v1_path}\nV2: {v2_path}")


if __name__ == "__main__":
    ingest_repos(
        "https://github.com/trimble-oss/modus-web-components.git",
        "https://github.com/Trimble-Construction/modus-wc-2.0.git",
    )
