import abc
import glob
import math
import os

import torch
import torchvision.transforms as transforms
from torch.nn.parallel.data_parallel import DataParallel
from torch.utils.data import DataLoader

from config import cfg
from logger import ColorLogger
from model import get_model
from timer import Timer


# import dataset class
exec("from " + cfg.train_set + " import " + cfg.train_set)
exec("from " + cfg.test_set + " import " + cfg.test_set)


class Base(metaclass=abc.ABCMeta):
	def __init__(self, log_name="logs.txt"):
		self.cur_epoch = 0

		# timer
		self.tot_timer = Timer()
		self.gpu_timer = Timer()
		self.read_timer = Timer()

		# logger
		self.logger = ColorLogger(cfg.log_dir, log_name=log_name)

	@abc.abstractmethod
	def _make_batch_generator(self):
		pass

	@abc.abstractmethod
	def _make_model(self):
		pass


class Trainer(Base):
	def __init__(self):
		super(Trainer, self).__init__(log_name="train_logs.txt")

	def get_optimizer(self, model):
		model_params = filter(lambda p: p.requires_grad, model.parameters())
		optimizer = torch.optim.Adam(model_params, lr=cfg.lr)
		return optimizer

	def save_model(self, state, epoch):
		file_path = os.path.join(cfg.model_dir, "snapshot_{}.pth.tar".format(str(epoch)))
		torch.save(state, file_path)
		self.logger.info("Write snapshot into {}".format(file_path))

	def load_model(self, model, optimizer):
		model_file_list = glob.glob(os.path.join(cfg.model_dir, "*.pth.tar"))
		cur_epoch = max(
			[
				int(file_name[file_name.find("snapshot_") + 9: file_name.find(".pth.tar")])
				for file_name in model_file_list
			]
		)
		checkpoint_path = os.path.join(cfg.model_dir, "snapshot_" + str(cur_epoch) + ".pth.tar")
		checkpoint = torch.load(checkpoint_path)
		start_epoch = checkpoint["epoch"] + 1
		model.load_state_dict(checkpoint["network"], strict=False)
		optimizer.load_state_dict(checkpoint['optimizer'])

		self.logger.info("Load checkpoint from {}".format(checkpoint_path))
		return start_epoch, model, optimizer

	def set_lr(self, epoch):
		for e in cfg.lr_dec_epoch:
			if epoch < e:
				break
		if epoch < cfg.lr_dec_epoch[-1]:
			idx = cfg.lr_dec_epoch.index(e)
			for g in self.optimizer.param_groups:
				g["lr"] = cfg.lr * (cfg.lr_dec_factor**idx)
		else:
			for g in self.optimizer.param_groups:
				g["lr"] = cfg.lr * (cfg.lr_dec_factor ** len(cfg.lr_dec_epoch))

	def get_lr(self):
		for g in self.optimizer.param_groups:
			cur_lr = g["lr"]
		return cur_lr

	def _make_batch_generator(self):
		# data load and construct batch generator
		self.logger.info("Creating dataset...")
		train_dataset = eval(cfg.train_set)(transforms.ToTensor(), "train")
		self.train_dataset = train_dataset
		self.itr_per_epoch = math.ceil(len(train_dataset) / cfg.num_gpus / cfg.train_batch_size)
		self.train_dataloader = DataLoader(
			dataset=train_dataset,
			batch_size=cfg.num_gpus * cfg.train_batch_size,
			shuffle=True,
			num_workers=cfg.num_thread,
			pin_memory=True,
		)

	def _make_model(self):
		# prepare network
		self.logger.info("Creating graph and optimizer...")
		model = get_model("train")

		model = DataParallel(model).cuda()
		optimizer = self.get_optimizer(model)
		if cfg.continue_train:
			start_epoch, model, optimizer = self.load_model(model, optimizer)
		else:
			start_epoch = 0

		self.start_epoch = start_epoch
		self.model = model
		self.optimizer = optimizer

	def initialize(self):
		self._make_batch_generator()
		self._make_model()
	
	def _evaluate(self, outs, cur_sample_idx):
		eval_result = self.train_dataset.evaluate(outs, cur_sample_idx)
		return eval_result

	def _get_evaluate_result(self):
		return self.train_dataset.get_eval_result()


class Tester(Base):
	def __init__(self, test_epoch):
		self.test_epoch = int(test_epoch)
		super(Tester, self).__init__(log_name="test_logs.txt")

	def _make_batch_generator(self):
		# data load and construct batch generator
		self.logger.info("Creating dataset...")
		self.test_dataset = eval(cfg.test_set)(transforms.ToTensor(), "test")
		self.dataloader = DataLoader(
			dataset=self.test_dataset,
			batch_size=cfg.num_gpus * cfg.test_batch_size,
			shuffle=False,
			num_workers=cfg.num_thread,
			pin_memory=True,
		)

	def _make_model(self):
		model_path = os.path.join(cfg.model_dir, "snapshot_%d.pth.tar" % self.test_epoch)
		assert os.path.exists(model_path), "Cannot find model at " + model_path
		self.logger.info("Load checkpoint from {}".format(model_path))

		# prepare network
		self.logger.info("Creating graph...")
		model = get_model("test")
		model = DataParallel(model).cuda()
		checkpoint = torch.load(model_path)
		model.load_state_dict(checkpoint["network"], strict=False)

		self.model = model

	def initialize(self):
		self._make_batch_generator()
		self._make_model()

	def _evaluate(self, outs, cur_sample_idx):
		eval_result = self.test_dataset.evaluate(outs, cur_sample_idx)
		return eval_result

	def _print_eval_result(self, test_epoch):
		self.test_dataset.print_eval_result(test_epoch)
