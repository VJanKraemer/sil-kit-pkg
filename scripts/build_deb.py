#! /bin/env python3
import argparse
import logging
import shutil
import subprocess
import re

from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SilKitVersion:
    major: int
    minor: int
    patch: int
    debian_suffix: str

@dataclass
class SilKitInfo:
    silkit_source_url: str
    silkit_source_ref: str
    silkit_source_path: Path
    is_local: bool
    recursive: bool

@dataclass
class BuildInfo:

    silkit_pkg_path: Path
    silkit_info: SilKitInfo
    version: str
    work_dir: Path
    silkit_version: SilKitVersion
    keep_temp: bool
    output_dir: Path

@dataclass
class BuildFlags:
    add_platform_flags: str
    add_debuild_flags: str
    c_compiler: str
    cxx_compiler: str

logger = logging.getLogger(__name__)

def create_arg_parser() -> ArgumentParser:
    ap = ArgumentParser("BuildPackages")
    ap.add_argument("--ubuntu-version", type=str, required=True)
    ap.add_argument("--silkit-pkg-path", type=Path, required=True)
    ap.add_argument("--silkit-pkg-tag", type=str, required=False)
    ap.add_argument("--silkit-source-url", type=str, required=True)
    ap.add_argument("--silkit-source-ref", type=str, required=True)
    ap.add_argument("--verbose", action='store_true', required=False)
    ap.add_argument("--keep-temp", action='store_true', required=False, default=False)
    ap.add_argument("--output-dir", type=str, required=False, default=Path.cwd() / 'output')

    return ap

def cleanup(build_info: BuildInfo, exitCode: int):
    
    silkit_info = build_info.silkit_info
    if silkit_info.is_local == False and silkit_info.silkit_source_path != None:
        shutil.rmtree(silkit_info.silkit_source_path, ignore_errors=True)

    if build_info.work_dir != None and build_info.keep_temp == False:
        shutil.rmtree(build_info.work_dir.resolve())

    exit(exitCode)

def generate_buildinfo(args) -> BuildInfo:
    build_info = BuildInfo(
            silkit_pkg_path=Path(args.silkit_pkg_path),
            silkit_info=SilKitInfo(
                silkit_source_url=args.silkit_source_url,
                silkit_source_ref=args.silkit_source_ref,
                silkit_source_path=None,
                is_local=False,
                recursive=True),
            version=None,
            work_dir=None,
            silkit_version=None,
            keep_temp = args.keep_temp,
            output_dir= args.output_dir
    )
    logger.debug(f"build_info: {build_info}")
    return build_info

def clone_silkit(build_info: BuildInfo):
    repoUrl = build_info.silkit_info.silkit_source_url
    repoPath = build_info.work_dir / 'sil-kit'
    repoRef = build_info.silkit_info.silkit_source_ref
    try:
        build_info.silkit_info.silkit_source_path = repoPath
        subprocess.run(['git', 'init', repoPath], check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', build_info.silkit_info.silkit_source_url],
                       cwd=repoPath,
                       check=True)
        result = subprocess.run(['git', 'fetch', '--no-tags', '--prune',
                        '--no-recurse-submodules', '--depth=1', 'origin',
                        repoRef],
                                cwd=repoPath,
                                check=True)
        subprocess.run(['git', 'checkout', '--progress', '--force', repoRef],
                       cwd=repoPath,
                       check=True)

        if build_info.silkit_info.recursive == True:
            logger.debug("Syncing the submodules!")
            subprocess.run(['git', 'submodule', 'sync', '--recursive'],
                           cwd=repoPath,
                           check=True)
            subprocess.run(['git', 'submodule', 'update', '--init', '--depth=1', '--recursive'],
                           cwd=repoPath,
                           check=True)

    except Exception as ex:
        logger.error(f"While cloning the SilKit Repo something occured: {str(ex)}")
        cleanup(build_info)


def get_silkit_repo(build_info: BuildInfo):
    
    # Check whether the repo is already checked out!
    repoPath = Path(build_info.silkit_info.silkit_source_url)
    logger.debug(f"Checking {repoPath}")

    if repoPath.exists():

        git_dir = repoPath / '.git'

        if not git_dir.exists():
            logger.error("The sil-kit path does exist, but is no GIT repo! Exiting!")
            cleanup(build_info, 64)
        
        # Copy sil-kit-dir
        try:
            shutil.copytree(repoPath, build_info.work_dir / repoPath)
        except Exception as ex:
            logger.error("Could not copy the sil-kit source tree into the workspace dir! Exiting")
            logger.debug(f"Python Exception: {str(ex)}")
            cleanup(build_info, 64)

        build_info.silkit_info.silkit_source_path = repoPath
        build_info.silkit_info.is_local = True
    else:
        clone_silkit(build_info)

def check_debian_directory(build_info: BuildInfo):
    
    debian_path = build_info.silkit_pkg_path / 'debian'
    logger.debug(f"Checking {debian_path.expanduser()}")
    if not debian_path.expanduser().exists():
        logger.error("The sil-kit-pkg/debian path does not exist! Exiting!")
        cleanup(build_info, 64)
    else:
        logger.info("Found the debian dir!")

def get_deb_version(build_info: BuildInfo):

    pattern = re.compile('^libsilkit \(([0-9]+)\.([0-9]+)\.([0-9]+)-([0-9]+).*')
    
    changelog_path = build_info.silkit_pkg_path.expanduser() / 'debian/changelog'
    logger.debug(f"Checking {changelog_path}")
    if not changelog_path.expanduser().exists():
        logger.error("Could not find Package Changelog! Exiting!")
        cleanup(build_info, 64)
    
    with open(changelog_path) as f:
        for line in f:
            result = re.match(pattern, line)
            if result:
                build_info.silkit_version = SilKitVersion(
                    major=result.group(1),
                    minor=result.group(2),
                    patch=result.group(3),
                    debian_suffix=result.group(4))

            logger.debug(f'SilKitVersion: {build_info.silkit_version}')
            return

def create_work_directory() -> Path:

    work_dir = Path.cwd() / 'package_workspace';
    logger.debug(f"Creating {work_dir} work dir!")

    try:
        Path.mkdir(work_dir, exist_ok=True)
        return work_dir
    except Exception as ex:
        logger.error(f"While creating the workdir an error occured: {str(ex)}")
        # No need for cleanup, nothing of value created yet
        exit(64)

def create_orig_tarball(build_info: BuildInfo):
    
    silkit_version = build_info.silkit_version

    if silkit_version == None:
        logger.error("No valid SilKit Version found! Exiting!")
        cleanup(build_info, 64)

    tarball_name = 'libsilkit_{}.{}.{}.orig.tar.gz'.format(
            silkit_version.major,
            silkit_version.minor,
            silkit_version.patch)
    try:
        subprocess.run(['tar', '--exclude=.git', '-czf', build_info.work_dir/tarball_name,
                        '-C', build_info.silkit_info.silkit_source_path, '.'], check=True)
    except Exception as ex:
        logger.error(f"While creating the orig tarball, an error occured!\n{str(ex)}")
        cleanup(build_info, 64)

def copy_debian_dir(build_info: BuildInfo):
    
    # Copy debian dir
    try:
        shutil.copytree(build_info.silkit_pkg_path.expanduser() / 'debian/', build_info.work_dir / 'sil-kit/debian')
    except Exception as ex:
        logger.error("Could not copy the debian dir into the sil kit source dir! Exiting")
        logger.debug(f"Python Exception: {str(ex)}")
        cleanup(build_info, 64)

def get_build_flags(ubuntu_version: str) -> BuildFlags:
    
    logger.info(f"Building for platform: {ubuntu_version}")
    if ubuntu_version == "20.04":
        return BuildFlags(
                add_platform_flags="",
                add_debuild_flags="-d --prepend-path=/opt/vector/bin",
                c_compiler="clang-10",
                cxx_compiler="clang++-10")
    if ubuntu_version == "22.04":
        return BuildFlags(
                add_platform_flags="-gdwarf-4",
                add_debuild_flags="",
                c_compiler="clang",
                cxx_compiler="clang++")
    if ubuntu_version == "24.04":
        return BuildFlags(
                add_platform_flags="",
                add_debuild_flags="",
                c_compiler="clang",
                cxx_compiler="clang++")
    
    return None

def build_package(build_flags: BuildFlags, build_info: BuildInfo):

    
    debuild_cmd = ['debuild',
                build_flags.add_debuild_flags, 
                f'--set-envvar=PLATFORM_BUILD_FLAGS={build_flags.add_platform_flags}',
                f'--set-envvar=CC={build_flags.c_compiler}',
                f'--set-envvar=CXX={build_flags.cxx_compiler}',
                '-us',
                '-uc',
                '--lintian-opts',
                '-E',
                '--pedantic']

    # If we have '' empty strings in the command list, strange things happen in
    # exec land
    debuild_cmd = list(filter(lambda arg: arg != '', debuild_cmd))

    logger.debug(f"Calling: {' '.join(debuild_cmd)}")
    subprocess.run(debuild_cmd,
                check=True,
                cwd=build_info.work_dir / 'sil-kit/')

def copy_artifacts(build_info: BuildInfo):

    try:
        Path.mkdir(build_info.output_dir, exist_ok=True)
    except Exception as ex:
        logger.error(f"Cannot create output dir {build_info.output_dir}")
        logger.error(f"mkdir: {str(ex)}")
        return

    file_list = (p.resolve() for p in build_info.work_dir.iterdir() if re.search(r"(.*\.build.*$)|(.*\.changes$)|(.*\..*deb$)|(.*\.dsc$)", p.suffix))

    for file in file_list:
        shutil.copy2(file, build_info.output_dir)

def main():
    arg_parser = create_arg_parser()
    args =arg_parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    build_info = generate_buildinfo(args)

    build_info.work_dir = create_work_directory()
    get_silkit_repo(build_info)
    check_debian_directory(build_info)
    get_deb_version(build_info)
    create_orig_tarball(build_info)
    copy_debian_dir(build_info)
    build_flags = get_build_flags(args.ubuntu_version)
    logger.info(f"Got build_flags: {build_flags}")
    build_package(build_flags, build_info)
    copy_artifacts(build_info)
    cleanup(build_info, 0)

if __name__ == '__main__':
    main()

