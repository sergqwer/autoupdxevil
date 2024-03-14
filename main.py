import time
import aiohttp
import asyncio
from diskcache import Cache
import aiofiles
import zipfile
import shutil
import json
import psutil
import os
import subprocess
from loguru import logger
import sys
from contextlib import suppress


def get_folders_in_directory(directory):
    folders = [folder for folder in os.listdir(directory) if os.path.isdir(os.path.join(directory, folder))]
    return folders


async def kill_process(process_name="XEvil.exe"):
    for _ in range(10):
        is_xevil = False
        for process in psutil.process_iter(['pid', 'name']):
            if process.info['name'] == process_name:
                is_xevil = True
                pid = process.info['pid']
                psutil.Process(pid).terminate()
                logger.info(f"Process {process_name} (PID: {pid}) terminated.")
                await asyncio.sleep(5)
        if not is_xevil:
            break

async def read_json(file_name):
    async with aiofiles.open(file_name, 'r') as f:
        data = await f.read()
        json_data = json.loads(data)
        return json_data

cache = Cache("tmp//cache")
lock = asyncio.Lock()

if "version" in cache:
    version = cache.get('version')
    logger.info(f"Last Update - {version}")
else:
    cache.set('version', '58')
    version = cache.get('version')
    logger.info(f"Last Update - {version}")

if "size" in cache:
    size = cache.get('size')
    logger.info(f"Last Size - {size}")
else:
    cache.set('size', '0')
    size = cache.get('size')
    logger.info(f"Last Size - {size}")

async def get_remote_file_size(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as response:
                if response.status == 200:
                    if 'Content-Length' in response.headers:
                        file_size = int(response.headers['Content-Length'])
                        return file_size
                    else:
                        return None
                else:
                    return None
    except Exception as e:
        logger.info(f"Error: {e}")
        return None


async def download_file(url, file_name):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(file_name, 'wb') as f:
                    total_size = int(response.headers.get('Content-Length', 0))

                    if os.path.exists("last_update.zip"):
                        file_size = os.path.getsize("last_update.zip")
                        if file_size == total_size:
                            return None

                    now_ind = 0

                    downloaded_size = 0
                    with suppress(Exception):
                        while True:
                            now_ind += 1
                            chunk = await response.content.read(1024)
                            if not chunk:
                                break
                            await f.write(chunk)
                            downloaded_size += len(chunk)
                            progress = downloaded_size / total_size * 100 if total_size else 0
                            if now_ind == 1000:
                                now_ind = 0
                                print(f"\rDownloaded: {downloaded_size} bytes / {total_size} bytes ({progress:.2f}%)", end="", flush=True)
                        print("")
            else:
                raise ValueError(f"Failed to download file. Status code: {response.status}")


async def extract_file(file_name, extract_dir):
    if not os.path.exists(extract_dir):
        os.makedirs(extract_dir)
    shutil.rmtree(extract_dir)
    with zipfile.ZipFile(file_name, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)


def copy_files_recursively(source_dir, destination_dir):
    for root, _, files in os.walk(source_dir):
        for filename in files:
            source_file = os.path.join(root, filename)
            relative_path = os.path.relpath(source_file, source_dir)
            destination_file = os.path.join(destination_dir, relative_path)
            if os.path.exists(destination_file):
                os.replace(source_file, destination_file)
            else:
                os.makedirs(os.path.dirname(destination_file), exist_ok=True)
                os.replace(source_file, destination_file)


async def start_update_xevil(file_url, xevil_path):
    file_name = "last_update.zip"
    file_dir = "last_update"
    logger.info("Starting Update Xevil....")
    logger.info("Download Update")
    await download_file(file_url, file_name)
    logger.info("File downloaded")
    logger.info("Starting to unzip the file")
    await extract_file(file_name, file_dir)
    logger.info("File is unpacked")
    logger.info("Stop Xevil")
    await kill_process()
    await asyncio.sleep(3)
    folders = get_folders_in_directory(os.path.join(xevil_path, "Modules/x64"))
    logger.info("Cleaning the update from unnecessary files")
    for a in get_folders_in_directory(file_dir + "/Modules/x64"):
        if a in folders:
            try:
                os.remove(os.path.join(file_dir + "/Modules/x64", a, "core.ini"))
            except:
                pass
    try:
        os.remove(os.path.join(file_dir, "XEvil.ini"))
    except:
        pass
    try:
        os.remove(os.path.join(file_dir, "RecapModule.ini"))
    except:
        pass
    logger.info("Update of Xevil files")
    copy_files_recursively(file_dir, xevil_path)

    logger.info("Run Xevil")
    subprocess.Popen([os.path.join(xevil_path, "XEvil.exe")])

    logger.info("Good Update")


async def check_new_version(last_version):
    for_return = last_version
    last_version = int(last_version)

    for _ in range(0, 100):
        new_version = last_version + 1
        file_url = f"http://dwld.org/files/XEvil6.0_[Beta{str(new_version)}]_patch.zip"
        file_size = None
        file_size = await get_remote_file_size(file_url)
        if file_size is not None:
            for_return = str(new_version)
        else:
            break
    return for_return



async def main():
    config = await read_json("config.json")
    xevil_path = config["path_xevil"]

    if os.path.exists(os.path.join(xevil_path, "XEvil.exe")):
        pass
    else:
        logger.info("Wrong path to the folder with Xevil in the configuration")

    time_check_last_version = 0

    while True:
        try:
            version = cache.get('version')
            if time.time() - time_check_last_version > 600:
                time_check_last_version = time.time()
                new_version = await check_new_version(version)
                if new_version != version:
                    logger.info("NEW VERSION !!!")
                    cache.set('version', new_version)
                    version = new_version

            file_url = f"http://dwld.org/files/XEvil6.0_[Beta{version}]_patch.zip"
            file_size = await get_remote_file_size(file_url)

            if file_size is not None:
                size = cache.get('size')
                if size != str(file_size):

                    await start_update_xevil(file_url, xevil_path)

                    cache.set('size', str(file_size))
                else:
                    logger.info("No need for updates")
            await asyncio.sleep(60)
        except Exception as e:
            logger.info(e)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())