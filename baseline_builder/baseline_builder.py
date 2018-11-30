import json
import sys
import os
from git import Repo, GitCommandError
import docker
import requests
import re
from subprocess import call

def retrieve_pr(repository_name, pr):
    github_api_token = os.environ["GITHUB_API_TOKEN"]
    r = requests.get("https://api.github.com/repos/" + repository_name + "/pulls/" + pr, headers={'Authorization': 'token ' + github_api_token, 'User-Agent': 'dojot-baseline-builder'})
    if "body" in r.json():
        pr_comment = r.json()["body"] 
        title =  r.json()["title"]
        reg = re.compile("(dojot\/dojot#.[0-9]+)")
        ret = reg.findall(pr_comment)
        return [title, ret]
    else:
        return ["PR not found", "none"]

def build_backlog_message(repo, repository_name, last_commit, current_commit):
    offset = 0
    commit_it = list(repo.iter_commits(current_commit, max_count=1, skip=offset))[0]
    messages = []
    message = ""
    print("Building backlog messages for repository " + repository_name)
    while commit_it.hexsha != last_commit:
        commit_it = list(repo.iter_commits(current_commit, max_count=1, skip=offset))[0]
        searchObj = re.match("Merge pull request #(.*) from .*", commit_it.message)
        if searchObj:
            pr = searchObj.group(1)
            message = repository_name + "#" + pr
            print("Retrieving information for PR " + message)
            title, issues = retrieve_pr(repository_name, pr)
            if issues:
                message += ", fixing"
                for issue in issues:
                    message += " " + issue
            message += ": " + title
            messages.append(message)
        offset = offset + 1
    if messages:
        message = repository_name + "\n"
        for _c in repository_name: message += "-"
        message += "\n\n"
        for m in messages:
            message += m + "\n"
    return message

def build_backlog_messages(spec, selected_repo):
    message = ""
    for repo_config in spec["components"]:
        repository_name = repo_config['repository-name']
        github_repository = repo_config['github-repository']

        if selected_repo != "all" and repository_name != selected_repo:
            print("Skipping " + repository_name + " from merging.")
            continue

        last_commit = repo_config["last-commit"]
        current_commit = repo_config["current-commit"]
        repository_dest = "./git_repos/"+repository_name
        repo = Repo(repository_dest)
        repo_message = build_backlog_message(repo, github_repository, last_commit, current_commit)
        if repo_message:
            repo_message += "\n\n"
        message += repo_message
    print("Backlog is:\n\n")
    print(message)

def checkout_git_repositories(spec, selected_repo):
    print("Checking out repositories...")
    username = os.environ["GITHUB_USERNAME"]
    usertoken = os.environ["GITHUB_TOKEN"]
    github_preamble = "https://" + username + ":" + usertoken + "@github.com/"
    print("Creating output directory...")
    try:
        os.stat("./git_repos")
    except:
        os.mkdir("./git_repos")
    print("... output repository directory created.")

    for repo_config in spec["components"]:
        repository_name = repo_config['repository-name']

        if selected_repo != "all" and repository_name != selected_repo:
            print("Skipping " + repository_name + " from checkout.")
            continue

        repository_url = github_preamble + repo_config['github-repository']
        repository_dest = "./git_repos/"+repo_config['repository-name']
        commit_id = repo_config['current-commit']

        print("Checking out " + repository_name)
        print("From GitHub repository " + repo_config['github-repository'])
        print("At commit " + commit_id)

        print("Cloning repository...")
        repo = Repo.clone_from(repository_url, repository_dest)
        print("... repository was cloned")

        print("Creating branch...")
        repo.head.reference = repo.create_head('baseline', commit_id)
        repo.head.reset(index=True, working_tree=True)
        print("... 'baseline' branch was created")
    print("... repositories were checked out.")


def create_git_tag(spec, selected_repo):
    print("Creating tag for all repositories...")
    baseline_tag_name = spec["tag"]
    for repo_config in spec["components"]:
        repository_name = repo_config['repository-name']

        if selected_repo != "all" and repository_name != selected_repo:
            print("Skipping " + repository_name + " from creating tag.")
            continue

        repository_dest = "./git_repos/"+repo_config['repository-name']
        repo = Repo(repository_dest)
        baseline_head = repo.heads['baseline']

        print("Creating tag for repository " + repository_name + "...")
        print("Checking whether tag has already been created...")

        if (baseline_tag_name in repo.tags):
            print("... tag has been already created.")
            print("... skipping repository " + repository_name + ".")
            continue
        else:
            print("... tag is not created yet. Good to go.")

        print("Creating baseline tag...")
        repo.create_tag(baseline_tag_name, ref=baseline_head,
                        message="Baseline: " + baseline_tag_name)
        print("... baseline tag was created.")
        print("... repository " + repository_name +
                " was properly tagged.")
    print("... all repositories were tagged.")


def push_git_tag(spec, selected_repo):
    print("Pushing everything to GitHub...")
    baseline_tag_name = spec["tag"]
    for repo_config in spec["components"]:
        repository_name = repo_config['repository-name']

        if selected_repo != "all" and repository_name != selected_repo:
            print("Skipping " + repository_name + " from pushing tag.")
            continue

        repository_dest = "./git_repos/"+repo_config['repository-name']
        repo = Repo(repository_dest)
        print("Pushing tag to repository " + repository_name + "...")

        print("Pushing baseline tag...")
        baseline_tag = repo.tags[baseline_tag_name]
        repo.remotes.origin.push(baseline_tag)
        print("... baseline tag was pushed.")

        print("... all changes were pushed to " + repository_name + ".")
    print("... everything was pushed to GitHub.")


def create_docker_baseline(spec, selected_repo):
    client = docker.from_env()
    docker_username = os.environ["DOCKER_USERNAME"]
    docker_password = os.environ["DOCKER_TOKEN"]
    print("Logging into Docker Hub...")
    client.login(docker_username, docker_password)
    print("... logged in.")
    for repo_config in spec["components"]:
        repository_name = repo_config['repository-name']

        if selected_repo != "all" and repository_name != selected_repo:
            print("Skipping " + repository_name +
                  " from pushing Docker images.")
            continue

        for docker_repo in repo_config["docker-hub-repositories"]:
            docker_name = docker_repo["name"]
            dockerfile = docker_repo["dockerfile"]
            baseline_tag_name = spec["tag"]
            repository_dest = "./git_repos/"+repo_config['repository-name']

            print("Building image for " + docker_name)
            os.system("docker build -t " + docker_name + ":" + baseline_tag_name + " --no-cache -f " + repository_dest + "/" + dockerfile + " " + repository_dest)

            print("Pushing new tag...")
            client.images.push(docker_name + ":" + baseline_tag_name)
            print("... pushed.")


def main():
    print("Starting baseline builder...")

    failed = False
    if "GITHUB_USERNAME" not in os.environ:
        print("GITHUB_USERNAME variable is missing.")
        failed = True
    if "GITHUB_TOKEN" not in os.environ:
        print("GITHUB_TOKEN variable is missing.")
        failed = True
    if "GITHUB_API_TOKEN" not in os.environ:
        print("GITHUB_API_TOKEN variable is missing.")
        failed = True
    if "DOCKER_USERNAME" not in os.environ:
        print("DOCKER_USERNAME variable is missing.")
        failed = True
    if "DOCKER_TOKEN" not in os.environ:
        print("DOCKER_TOKEN variable is missing.")
        failed = True
    if failed:
        exit(1)

    print("Reading baseline spec file...")
    raw_spec = open("baseline-spec.json", "r")
    # Treat exceptions
    spec = json.loads(raw_spec.read())
    if len(sys.argv) == 1:
        checkout_git_repositories(spec, "all")
    elif len(sys.argv) == 3:
        selected_repo = sys.argv[2]
        if sys.argv[1] == "checkout":
            checkout_git_repositories(spec, selected_repo)
        if sys.argv[1] == "backlog":
            build_backlog_messages(spec, selected_repo)
        if sys.argv[1] == "docker":
            create_docker_baseline(spec, selected_repo)
        else:
            print("Unknown command.")
    else:
        print(
            "Usage: " + sys.argv[0] +
            " [checkout | backlog | docker] [REPOSITORY | 'all']")


if __name__ == "__main__":
    main()
