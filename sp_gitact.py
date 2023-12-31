import os
import argparse
import zipfile
import shutil
from huggingface_hub import login, HfApi

from waifuc.action import FirstNSelectAction, \
    ModeConvertAction, RandomFilenameAction, AlignMinSizeAction
from waifuc.export import SaveExporter
from page_source import AnimePicturesPageSource, ZerochanPageSource
from waifuc.source.anime_pictures import OrderBy
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED, ALL_COMPLETED


def spider(start, end, save_step):
    #s = AnimePicturesPageSource([], order_by=OrderBy.DATE)
    s = ZerochanPageSource([])
    s.set_page_range(start, end)

    # crawl images, process them, and then save them to directory with given format
    s.attach(
        # preprocess images with white background RGB
        ModeConvertAction('RGB', 'white'),

        # if min(height, weight) > 800, resize it to 800
        AlignMinSizeAction(1024),

        # FilterSimilarAction('all'),  # filter again
        #FirstNSelectAction(100),  # first 200 images
        RandomFilenameAction(ext='.webp'),  # random rename files
    ).export(
        # save to surtr_dataset directory
        SaveExporter(f'data_v1/group{start//save_step}/page{start}-{end}')
    )

def upload_to_hf(api, gid):
    # 把 gid 这个组压缩
    zip_file = zipfile.ZipFile(f'group{gid}.zip', 'w', zipfile.ZIP_DEFLATED)

    startdir = f'data_v1/group{gid}'
    for dirpath, dirnames, filenames in os.walk(startdir):
        fpath = dirpath.replace(startdir, '')  # 这一句很重要，不replace的话，就从根目录开始复制
        fpath = fpath and fpath+os.sep or ''  # 这句话理解我也点郁闷，实现当前文件夹以及包含的所有文件的压缩
        for filename in filenames:
            zip_file.write(os.path.join(dirpath, filename), fpath+filename)
    zip_file.close()

    # 删除图片文件夹
    shutil.rmtree(f'data_v1/group{gid}')

    api.upload_file(
        path_or_fileobj=f'group{gid}.zip',
        path_in_repo=f'group{gid}.zip',
        repo_id="7eu7d7/AnimeUniverse",
        repo_type="dataset",
    )
    print(f'upload group{gid}.zip')
    os.remove(f'group{gid}.zip')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='anime dataset test1')
    parser.add_argument('--hf_token', type=str, default='')
    parser.add_argument('--start_page', type=int, default=0)
    parser.add_argument('--end_page', type=int, default=10000)
    parser.add_argument('--page_step', type=int, default=10)
    parser.add_argument('--save_step', type=int, default=200)
    args = parser.parse_args()

    login(args.hf_token)
    api = HfApi()

    with ThreadPoolExecutor(max_workers=2) as t:
        all_task = [t.submit(spider, page*args.page_step, page*args.page_step+args.page_step, args.save_step) for page in
            range(args.start_page//args.page_step, args.end_page//args.page_step)]

        save_step = args.save_step//args.page_step
        task_group = [all_task[i:i+save_step] for i in range(0,len(all_task),save_step)]
        for gid, task in enumerate(task_group):
            wait(task, return_when=ALL_COMPLETED)
            upload_to_hf(api, gid)

        print('finished')
