"""People Counter."""
"""
 Copyright (c) 2018 Intel Corporation.
 Permission is hereby granted, free of charge, to any person obtaining
 a copy of this software and associated documentation files (the
 "Software"), to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish,
 distribute, sublicense, and/or sell copies of the Software, and to
 permit person to whom the Software is furnished to do so, subject to
 the following conditions:
 The above copyright notice and this permission notice shall be
 included in all copies or substantial portions of the Software.
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


import os
import sys
import time
import numpy as np
import socket
import json
import cv2

import logging as log
import paho.mqtt.client as mqtt

from argparse import ArgumentParser
from inference import Network


# MQTT server environment variables
HOSTNAME = socket.gethostname()
IPADDRESS = socket.gethostbyname(HOSTNAME)
MQTT_HOST = IPADDRESS
MQTT_PORT = 3001
MQTT_KEEPALIVE_INTERVAL = 60


def build_argparser():
    """
    Parse command line arguments.

    :return: command line arguments
    """
    parser = ArgumentParser()
    parser.add_argument("-m", "--model", required=True, type=str,
                        help="Path to an xml file with a trained model.")
    parser.add_argument("-i", "--input", required=True, type=str,
                        help="Path to image or video file")
    parser.add_argument("-l", "--cpu_extension", required=False, type=str,
                        default=None,
                        help="MKLDNN (CPU)-targeted custom layers."
                             "Absolute path to a shared library with the"
                             "kernels impl.")
    parser.add_argument("-d", "--device", type=str, default="CPU",
                        help="Specify the target device to infer on: "
                             "CPU, GPU, FPGA or MYRIAD is acceptable. Sample "
                             "will look for a suitable plugin for device "
                             "specified (CPU by default)")
    parser.add_argument("-pt", "--prob_threshold", type=float, default=0.5,
                        help="Probability threshold for detections filtering"
                        "(0.5 by default)")
    return parser


def connect_mqtt():
    ### TODO: Connect to the MQTT client ###
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL)

    return client

def draw_masks(frame, result, width, height, prob_threshold):
    '''
    Draw semantic mask classes onto the frame.
    '''
    people = 0
    probabilities = result[0, 0, :, 2]
    out_frame = frame
    for index, probability in enumerate(probabilities):
        if probability > prob_threshold:
            people += 1
            x1, y1, x2, y2 = result[0, 0, index, 3:]
            pt1 = (int(x1 * width), int(y1 * height))
            pt2 = (int(x2 * width), int(y2 * height))
            out_frame = cv2.rectangle(frame, pt1, pt2, (0, 0, 255), 2)
            
    out_frame = cv2.resize(out_frame, (768, 432))
    return out_frame, people


def infer_on_stream(args, client):
    """
    Initialize the inference network, stream video to network,
    and output stats and video.

    :param args: Command line arguments parsed by `build_argparser()`
    :param client: MQTT client
    :return: None
    """
    # Initialise the class
    infer_network = Network()
    # Set Probability threshold for detections
    prob_threshold = args.prob_threshold

    ### TODO: Load the model through `infer_network` ###
    infer_network.load_model(model=args.model, cpu_extension=args.cpu_extension)
    net_input_shape = infer_network.get_input_shape()
    
    ### TODO: Handle the input stream ###
    cap = cv2.VideoCapture(args.input)
    cap.open(args.input)
    
    # Grab the shape of the input 
    width = int(cap.get(3))
    height = int(cap.get(4))

    ### TODO: Loop until stream is over ###
    total_duration = 0
    duration = 0
    noPersonDetected = 0
    total_people = 0
    prev_count = 0
    start_time = None
    while cap.isOpened():
        total_duration += 1
        ### TODO: Read from the video capture ###
        flag, frame = cap.read()
        
        if not flag:
            break
        key_pressed = cv2.waitKey(60)
        
        ### TODO: Pre-process the image as needed ###
        p_frame = cv2.resize(frame, (net_input_shape[3], net_input_shape[2]))
        p_frame = p_frame.transpose(2, 0, 1)
        p_frame = p_frame.reshape(1, *p_frame.shape)

        ### TODO: Start asynchronous inference for specified request ###
        infer_network.exec_net(p_frame)

        ### TODO: Wait for the result ###
        if infer_network.wait() == 0:
            ### TODO: Get the results of the inference request ###
            result = infer_network.get_output()
            ### TODO: Extract any desired stats from the results ###
                    
            out_frame, people = draw_masks(frame, result, width, height, args.prob_threshold)
            
            if start_time is None and people > 0:
                start_time = time.time()
                prev_count = people
            
            ### TODO: Calculate and send relevant information on ###
            ### current_count, total_count and duration to the MQTT server ###
            ### Topic "person": keys of "count" and "total" ###
            ### Topic "person/duration": key of "duration" ###
#             client.publish("person", json.dumps({"count": current_count, "total": total_count}))
#             client.publish("person/duration", json.dumps("duration": duration))
            if people > 0:
                duration += 1
                noPersonDetected = 0
                prev_count = people
            else:
                noPersonDetected += 1
                
            if start_time is not None and noPersonDetected >= 10:
                total_people += 1
                prev_count = 0
                total_duration = time.time() - start_time
                client.publish("person/duration", json.dumps({"duration": total_duration}))
                start_time = None
                people = 0
                duration = 0
            
            
            log.warning("total duration: %s,\n Duration: %s", total_duration // 10, duration // 10)
            # client.publish("person", json.dumps({"count": people, "total": total_people}))
            client.publish("person", json.dumps({"count": people, "total": total_people}))

        ### TODO: Send the frame to the FFMPEG server ###
        sys.stdout.buffer.write(out_frame)
        sys.stdout.flush()

        ### TODO: Write an output image if `single_image_mode` ###
        
        if key_pressed == 27:
            break
    # release the cam and destory any camera window
    cap.release()
    cv2.destroyAllWindows()
    # disconnect MQTT server.
    client.disconnect()


def main():
    """
    Load the network and parse the output.

    :return: None
    """
    # Grab command line args
    args = build_argparser().parse_args()
    # Connect to the MQTT server
    client = connect_mqtt()
    # Perform inference on the input stream
    infer_on_stream(args, client)


if __name__ == '__main__':
    main()
