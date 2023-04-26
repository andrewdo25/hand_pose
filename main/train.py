import argparse
import torch
import torch.backends.cudnn as cudnn

from config import cfg
from base import Trainer
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", type=str, dest="gpu_ids")
    parser.add_argument("--continue", dest="continue_train", action="store_true")
    parser.add_argument("--log_steps", default=100, type=int)
    args = parser.parse_args()

    if not args.gpu_ids:
        assert 0, "Please set proper gpu ids"

    if "-" in args.gpu_ids:
        gpus = args.gpu_ids.split("-")
        gpus[0] = int(gpus[0])
        gpus[1] = int(gpus[1]) + 1
        args.gpu_ids = ",".join(map(lambda x: str(x), list(range(*gpus))))

    return args


def main():
    # argument parse and create log
    args = parse_args()
    cfg.set_args(args.gpu_ids, args.continue_train)
    cudnn.benchmark = True

    trainer = Trainer()
    trainer._make_batch_generator()
    trainer._make_model()

    # train
    for epoch in range(trainer.start_epoch, cfg.end_epoch):
        trainer.set_lr(epoch)
        trainer.tot_timer.tic()
        trainer.read_timer.tic()
        for itr, (inputs, targets, meta_info) in tqdm(
            enumerate(trainer.batch_generator), desc=f"Epoch {epoch}/{cfg.end_epoch}:"
        ):
            # print('> Input shape', inputs['img'].size())
            trainer.read_timer.toc()
            trainer.gpu_timer.tic()

            # forward
            trainer.optimizer.zero_grad()
            loss = trainer.model(inputs, targets, meta_info, "train")
            loss = {k: loss[k].mean() for k in loss}

            # backward
            sum(loss[k] for k in loss).backward()
            trainer.optimizer.step()
            trainer.gpu_timer.toc()
            screen = [
                "Epoch %d/%d itr %d/%d:" % (epoch, cfg.end_epoch, itr, trainer.itr_per_epoch),
                "lr: %g" % (trainer.get_lr()),
                "speed: %.2f(%.2fs r%.2f)s/itr"
                % (
                    trainer.tot_timer.average_time,
                    trainer.gpu_timer.average_time,
                    trainer.read_timer.average_time,
                ),
                "%.2fh/epoch" % (trainer.tot_timer.average_time / 3600.0 * trainer.itr_per_epoch),
            ]
            screen += ["%s: %.4f" % ("loss_" + k, v.detach()) for k, v in loss.items()]

            if itr % args.log_steps == 0 or itr == len(trainer.batch_generator) - 1:
                trainer.logger.info(" ".join(screen))

            trainer.tot_timer.toc()
            trainer.tot_timer.tic()
            trainer.read_timer.tic()

        if (epoch + 1) % cfg.checkpoint_freq == 0 or epoch + 1 == cfg.end_epoch:
            trainer.save_model(
                {
                    "epoch": epoch,
                    "network": trainer.model.state_dict(),
                    "optimizer": trainer.optimizer.state_dict(),
                },
                epoch + 1,
            )
        # break


if __name__ == "__main__":
    main()
