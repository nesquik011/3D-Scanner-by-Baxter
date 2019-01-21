#!/usr/bin/env python
# -*- coding: utf-8 -*-

''' What this script does:
Compute RGB-D camera's location in Baxter's forearm frame:{ 
    Read in images from two camera: Baxter left hand camera, and RGB-D camera.
    Locate chessboard in each of their image.
    Obtain relative position between two cameras.
    Obtain the pose of RGB-D camera in the Baxter's forearm frame.
}
Save result:{ 
    Display the chessboard detection result.
    Wait for user's key.
    If pressed, saved the T_forearm_to_camera (rgb-d cam) to .yaml file.
}
'''

# -- Standard
import open3d
import numpy as np
import sys, os
import cv2
PYTHON_FILE_PATH=os.path.join(os.path.dirname(__file__))+"/"

# -- ROS
import rospy
from geometry_msgs.msg import Pose, Point, Quaternion
from sensor_msgs.msg import CameraInfo
from tf.transformations import euler_from_quaternion, quaternion_from_euler, euler_matrix
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError

# -- My lib
sys.path.append(PYTHON_FILE_PATH + "../../src_python")
from lib_geo_trans_ros import form_T, quaternion_to_R, toRosPose, pose2T
from lib_cam_calib import *
from lib_baxter import MyBaxter
from lib_keyboard_input import waitKeyPress

getStrBeforeLastChar = lambda s, c: s[:(-s[::-1].find(c))]

def sub_camera_info(image_topic):
    # change topic to info: "usb_cam/image_raw" -> "usb_cam/camera_info"
    image_topic = getStrBeforeLastChar(image_topic, '/')+'camera_info'
    camera_info = rospy.wait_for_message(image_topic, topic_type=CameraInfo)
    return camera_info

def sub_camera_K_and_D(image_topic):
    camera_info = sub_camera_info(image_topic)
    K = np.array(camera_info.K).reshape((3,3))
    D = np.array(camera_info.D)
    return K, D

def sub_image(image_topic):
    ros_image = rospy.wait_for_message(image_topic, topic_type=Image)
    cv2_img = CvBridge().imgmsg_to_cv2(ros_image, "bgr8")
    return cv2_img

def pubImage(publisher, cv2_image):
    publisher.publish(CvBridge().cv2_to_imgmsg(cv2_image, "bgr8"))

# -- Main
if __name__ == "__main__":
    rospy.init_node("calib_camera_pose")
    # TWO THINGS WE WANT!:
    T_baxter_to_chess = None
    T_arm_to_depth = None
    folder = rospy.get_param("file_folder")
    file_name1 = folder+rospy.get_param("file_name_T_baxter_to_chess")
    file_name2 = folder+rospy.get_param("file_name_T_arm_to_depth")

    # -- Get the two cameras topic.
    # -- Note: Both cameras are using color image for locating chessboard!!!
    DEBUG_MODE = True
    if DEBUG_MODE: # Use my usb cam to debug
        CAMERA_FOR_DEBUG = "usb_cam/image_raw"
        topic_cam_color = CAMERA_FOR_DEBUG
        topic_cam_depth = CAMERA_FOR_DEBUG
    else:
        topic_cam_color = rospy.get_param("topic_baxter_left_hand_camera")
        topic_cam_depth = rospy.get_param("topic_rgbd_camera")
        my_baxter = MyBaxter("left")
        THE_FRAME_DEPTHCAM_CONNECTED_TO = rospy.get_param("the_frame_depth_camera_connected_to")

    # -- Set a publisher for visualization chessboard in image
    debug_topic_to_pub_image_result = rospy.get_param("~debug_topic_to_pub_image_result")
    pub = rospy.Publisher(debug_topic_to_pub_image_result, Image, queue_size=5)

    # -- Set params 
    # Camera info
    K1, D1 = sub_camera_K_and_D(topic_cam_color)
    K2, D2 = sub_camera_K_and_D(topic_cam_depth)
    print "K1: ", K1
    print "D1: ", D1
    print "K2: ", K2
    print "D2: ", D2
    cameras=[(topic_cam_color, K1, D1), (topic_cam_depth, K2, D2)]

    # Chessboard
    SQUARE_SIZE = 0.0158
    CHECKER_ROWS = 7
    CHECKER_COLS = 9

    # -- Main Loop: locate rgb-d camera pose, wait for user's keypress to save it file
    while not rospy.is_shutdown():
        Is_disp=[]
        Rs=[]
        ps=[]
        rospy.loginfo("-------------------------------------------")

        # -- Subscribe to image and locate chessboard
        for i in range(2):
            image_topic, K, D = cameras[i][0],cameras[i][1],cameras[i][2]
            I = sub_image(image_topic)
            # rospy.loginfo("Subscribed a image from " + image_topic)
            res, R, p, imgpoints = getChessboardPose(I, K, D, SQUARE_SIZE , CHECKER_ROWS, CHECKER_COLS)
            
            # Draw to image
            img_display=I.copy()
            if res==True:
                drawChessboardToImage(img_display, imgpoints, CHECKER_ROWS, CHECKER_COLS)
                drawPosTextToImage(img_display, p)
                drawCoordinateToImage(img_display, R, p, K, D)

            # Return
            Is_disp.append(img_display)
            Rs.append(R)
            ps.append(p)

        # -- Display result
        I_disp = np.hstack([Is_disp[0], Is_disp[1]])
        pubImage(pub, I_disp)
        # rospy.loginfo("Published a new image with chessboard result")

        # -- Wait for user keypress to calib poses
        s1 = "Press key to compute transformations between Baxter_base, Baxter_forearm, Baxter_color_camera, depth_camera, and chessboard:"
        s2 = "Press a: compute T_Base_to_Chess ( from T_ColorCam_to_Chess )"
        s3 = "Press b: compute T_Arm_to_DepthCam ( from T_DepthCam_to_Chess )"
        print("\n"+s1+"\n"+s2+"\n"+s3)
        c = waitKeyPress(time_out=1.0)
        print("\n")

        if (c=='a'): # Return T_baxter_to_chess
            T_color_to_chess=form_T(Rs[0],ps[0])
            if DEBUG_MODE:
                T_baxter_to_color = np.identity(4)
            else:
                pos, quaternion = my_baxter.getCameraPose()
                T_baxter_to_color = pose2T(pos, quaternion)
            T_baxter_to_chess = T_baxter_to_color.dot(T_color_to_chess)
            print "Get/Save T_baxter_to_chess:\n", T_baxter_to_chess
            np.savetxt(file_name1, T_baxter_to_chess, delimiter=" ")

        elif(c=='b'): # Return T_arm_to_depth
            if T_baxter_to_chess is None:
                print("Please press a to compute T_baxter_to_chess first!")
            else:
                T_depth_to_chess=form_T(Rs[1],ps[1]) # from image processing
                if DEBUG_MODE:
                    T_baxter_to_arm = np.identity(4)
                else:
                    pos, quaternion = my_baxter.getFramePose(THE_FRAME_DEPTHCAM_CONNECTED_TO)
                    T_baxter_to_arm= pose2T(pos, quaternion)

                # Combine the above transformations
                T_chess_to_depth = np.linalg.inv(T_depth_to_chess)
                T_arm_to_baxter = np.linalg.inv(T_baxter_to_arm)

                T_arm_to_depth = T_arm_to_baxter.dot(T_baxter_to_chess).dot(T_chess_to_depth)
                print "Get/Save T_arm_to_depth:\n", T_arm_to_depth
                np.savetxt(file_name2, T_arm_to_depth, delimiter=" ")

        rospy.sleep(0.05)

    rospy.spin()


