#!/bin/bash

LOCAL_CODE=/home/cghg/andq/hand_pose/
IMAGE_CODE=/usr/src/app/

LOCAL_DATA=/media/local-data/andq/data/DEX_YCB/data/
IMAGE_DATA=/usr/src/app/data/DEX_YCB/data/

docker run --gpus all \
	--name andq-training \
	-it --ipc=host --rm \
	-p 8888:8888 \
	-v $LOCAL_CODE:$IMAGE_CODE \
	-v $LOCAL_DATA:$IMAGE_DATA \
	local/oru-dgx bash
