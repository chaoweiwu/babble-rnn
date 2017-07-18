from __future__ import print_function

from model_utils import ModelUtils
from model_def import ModelDef
from run_config import RunConfig
from keras.utils.data_utils import get_file
from keras import backend as K
import numpy as np
import time
import sys
import os
import signal
from generator import Generator

utils = ModelUtils()
model_def = None

config = RunConfig(utils)
config.load_config()

signal.signal(signal.SIGINT, utils.signal_handler)
signal.signal(signal.SIGTERM, utils.signal_handler)

# read an existing iteration counter if it exists
start_iteration = utils.read_iteration_count() or config.start_iteration
config.start_iteration = start_iteration

num_iterations = config.num_iterations
fit_batch_size = config.fit_batch_size
learn_next_step = config.learn_next_step
gen_every_nth = config.gen_every_nth
save_model_every_nth = config.save_model_every_nth
framelen=config.framelen
frame_seq_len = config.frame_seq_len
seed_seq_len = config.seed_seq_len

seq_step = config.seq_step or frame_seq_len
config.seq_step = seq_step

test_data_fn = utils.testdata_filename or config.test_data_fn
config.test_data_fn = test_data_fn

utils.log("loading test data from: ", test_data_fn)
testdata = np.fromfile(test_data_fn, dtype=np.uint8)

len_testdata = len(testdata)
num_frames = int(len_testdata / framelen)
utils.log('corpus length (bytes):', len_testdata)
utils.log('corpus length (frames):', num_frames)

config.log_attrs()
if not utils.generate_mode():
  config.save_config()

frame_seqs = []
next_frame_seqs = []
next_frames = []
all_frames = []




def normalize_input(frame):
  normframe = np.array(frame, dtype=np.float32)
  normframe = np.divide(normframe, ModelDef.frame_property_scaleup)
  return normframe

def gen_sequence(iteration):
  return (iteration % gen_every_nth == 0)

def save_model(iteration):
  return (iteration % save_model_every_nth == 0)

utils.log("scanning testdata into frames and frame sequences")

# step through the testdata, pulling those bytes into an array of all the the frames, all_frames
for j in range(0, num_frames):
    i = j * framelen   
    all_frames.append(normalize_input(testdata[i: i + framelen]))

utils.log('actual number of frames:', len(all_frames))

# pull the frames into frame sequences (frame_seqs), each of frame_seq_len frames
for i in range(0, num_frames - 2*frame_seq_len, seq_step):
    frame_seqs.append(all_frames[i: i + frame_seq_len])
    if learn_next_step:
        # pull a single frame following each frame sequence into a corresponding array of next_frames
        next_frames.append(all_frames[i + frame_seq_len])
    else:
        j = i + frame_seq_len
        next_frame_seqs.append(all_frames[j: j + frame_seq_len])
    

utils.log('number of frame sequences:', len(frame_seqs))


# make sure that the input and output frames are float32, rather than
# the unsigned bytes that we load from the corpus
print('initialising input and expected output arrays')
num_frame_seqs = len(frame_seqs)
X = np.zeros((num_frame_seqs, frame_seq_len, framelen), dtype=np.float32)
if learn_next_step:
    y = np.zeros((num_frame_seqs, framelen), dtype=np.float32)
else:
    y = np.zeros((num_frame_seqs, frame_seq_len, framelen), dtype=np.float32)



for i, frame_seq in enumerate(frame_seqs):
    if learn_next_step:
        # expected output is always the next frame for corresponding frame_seq
        y[i] = next_frames[i]
    else:
        y[i] = next_frame_seqs[i]
    
    
    # input is just each frame_seq 
    X[i] = frame_seq


####  Setup the model
model_def = utils.define_or_load_model(frame_seq_len, framelen, num_frame_seqs)


generator = Generator(utils, all_frames, seed_seq_len, utils.generate_len, learn_next_step)
generator.frame_property_scaleup = model_def.frame_property_scaleup
generator.framelen = framelen

# generator seed can start at various positions in the frame set
# command line parameters can force this in the following call
utils.setup_seed_start(generator)

# for generating a model, no training iterations are required
# just generate the data from the model and exit 
if utils.generate_mode():
  utils.log("Generating Samples")
  generator.generate(0)  
  exit()

# train the model
# output generated frames after nth iteration
for iteration in range(start_iteration, num_iterations + 1):
  print('-' * 50)
  
  
  utils.log('Training Iteration', iteration)
  
  model_def.before_iteration(iteration)
    

  model_def.model.fit(X, y, batch_size=fit_batch_size, nb_epoch=1,
   callbacks=[utils.csv_logger]
  )
  
  if gen_sequence(iteration):
    # every nth iteration generate sample data as a Codec 2 file

    utils.log("Generating samples")
    generator.generate(iteration)
  else:
    print("not generating samples this iteration")  
  
  if save_model(iteration):
    print("saving .h5 model file")
    utils.save_h5_model(iteration)
    print("saving .h5 weights file")      
    utils.save_weights(iteration)
    utils.write_iteration_count(iteration)
  else:
    print("not saving models this iteration")  

  print()


