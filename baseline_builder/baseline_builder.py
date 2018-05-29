import json
import os
from git import Repo
import docker


def create_git_baseline(spec):
    username = os.environ["GITHUB_USERNAME"]
    usertoken = os.environ["GITHUB_TOKEN"]
    baseline_tag_name = spec["tag"]
    github_preamble = f"https://{username}:{usertoken}@github.com/"
    print("Creating output directory...")
    try:
        os.stat("./git_repos")
    except:
        os.mkdir("./git_repos")
    print("... output repository directory created.")
    for repo_config in spec["components"]:
        repository_name = repo_config['repository-name']
        repository_url = github_preamble + repo_config['github-repository']
        repository_dest = "./git_repos/"+repo_config['repository-name']
        commit_id = repo_config['commit']

        print(f"Checking out {repository_name}")
        print(f"From GitHub repository {repo_config['github-repository']}")
        print(f"At commit {commit_id}")

        print("Cloning repository...")
        repo = Repo.clone_from(repository_url, repository_dest)
        print("... repository was cloned")

        print("Creating branch...")
        baseline_head = repo.create_head('baseline', commit_id)
        repo.head.reference = baseline_head
        repo.head.reset(index=True, working_tree=True)
        print("... 'baseline' branch was created")

        if repo_config["use-nightly"] == True:
            print("Checking out nightly mirror repository...")
            nightly_url = github_preamble + repo_config["nightly-repository"]
            nightly_branch = repo_config["nightly-branch"]
            nightly_repo = repo.create_remote("nightly", nightly_url)
            nightly_repo.fetch()
            nightly_head = repo.create_head(
                'baseline-nightly', "nightly/" + nightly_branch)
            repo.head.reference = nightly_head
            repo.head.reset(index=True, working_tree=True)
            print("... nightly mirror repository was cloned, branches updated.")
            print("Merging code with original repository commit...")
            merge_base = repo.merge_base(nightly_head, baseline_head)
            repo.index.merge_tree(nightly_head, base=merge_base)
            repo.index.commit("Merging from master",
                              parent_commits=(nightly_head.commit, baseline_head.commit))
            print("... merge was committed.")

            print("Pushing changes to nightly mirror repository...")
            repo.git.push("nightly", f"{nightly_head}:{nightly_branch}")

            print("Pushing baseline tag...")
            baseline_tag = repo.create_tag(baseline_tag_name, ref=nightly_head,
                                           message=f"Baseline: {baseline_tag_name}")

            repo.remotes.origin.push(baseline_tag)
            print("... everything was pushed to nightly mirror repository.")
        else:
            print("Pushing baseline tag...")
            baseline_tag = repo.create_tag(baseline_tag_name, ref=baseline_head,
                                           message=f"Baseline: {baseline_tag_name}")
            repo.remotes.origin.push(baseline_tag)
            print("... everything was pushed to repository.")


def create_docker_baseline(spec):
    client = docker.from_env()
    docker_username = os.environ["DOCKER_USERNAME"]
    docker_password = os.environ["DOCKER_PASSWORD"]
    print("Logging into Docker Hub...")
    client.login(docker_username, docker_password)
    print("... logged in.")
    for repo_config in spec["components"]:
        docker_repo = repo_config["docker-hub-repository"]
        docker_tag = repo_config["docker-hub-tag"]
        baseline_tag_name = spec["tag"]

        print(f"Pulling image {docker_repo}:{docker_tag}...")
        image = client.images.pull(docker_repo, tag=docker_tag)
        print("... image pulled.")
        print(f"Tagging it with {baseline_tag_name}...")
        image.tag(docker_repo, tag=baseline_tag_name)
        print("... tagged.")
        print("Pushing new tag...")
        client.images.push(docker_repo, tag=baseline_tag_name)
        print("... pushed.")


def main():
    print("Starting baseline builder...")

    print("Reading baseline spec file...")
    raw_spec = open("baseline-spec.json", "r")
    # Treat exceptions
    spec = json.loads(raw_spec.read())
    create_git_baseline(spec)
    create_docker_baseline(spec)


if __name__ == "__main__":
    main()
