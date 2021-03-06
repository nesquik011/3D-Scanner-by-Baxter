This is part of my [Winter Project at NWU](https://github.com/felixchenfy/Detect-Object-and-6D-Pose).


Object 3D Scanning by Baxter Robot
========================

![](doc/fig_scan_bottle_result.png)

Videos of scanning a bottle and a meter are put [here](https://github.com/felixchenfy/Data-Storage/raw/master/3D-Scan-by-Baxter/demo1_bottle_speedx3.mp4) and [here](https://github.com/felixchenfy/Data-Storage/raw/master/3D-Scan-by-Baxter/demo1_meter_speedx3.mp4).  
An animation is shown below:      
![](https://github.com/felixchenfy/Data-Storage/raw/master/3D-Scan-by-Baxter/demo1_bottle_speedx3.gif)



**Contents:**
<!-- TOC -->

- [Object 3D Scanning by Baxter Robot](#object-3d-scanning-by-baxter-robot)
- [1. Workflow](#1-workflow)
- [2. Communication between ROS nodes](#2-communication-between-ros-nodes)
  - [2.1. Overview](#21-overview)
  - [2.2. Node1: Move Baxter](#22-node1-move-baxter)
  - [2.3. Node2: Filter cloud](#23-node2-filter-cloud)
  - [2.4. Node3: Register clouds](#24-node3-register-clouds)
  - [2.5. Fake node1 for debug](#25-fake-node1-for-debug)
- [3. Algorithms](#3-algorithms)
  - [3.1. Calibrate poses of chessboard and depth_camera](#31-calibrate-poses-of-chessboard-and-depthcamera)
  - [3.2. Filter point cloud](#32-filter-point-cloud)
  - [3.3. Registration](#33-registration)
- [4. File Structure](#4-file-structure)
- [5. Dependencies and Installation](#5-dependencies-and-installation)
- [6. Problems to Solve](#6-problems-to-solve)
- [7. Reference](#7-reference)

<!-- /TOC -->

# 1. Workflow

Before 3D scanning:

1. Place a depth camera on Baxter's lower forearm.  
2. Place a chessboard on the table. 
3. Calibrate the pose of chessboard by Baxter's wrist camera. 
4. Calibrate the pose of the depth camera by (1) chessboard and (2) forward kinematics.
5. Place the object on the chessboard.

During 3D scanning:

1. Move Baxter's limb to several positions to take depth images from different view angles.
2. Filter the point clouds, and register them into a single 3D model.


# 2. Communication between ROS nodes

## 2.1. Overview
I wrote **1 ROS node** for calibration and **3 ROS nodes** for 3D scanning.

Use ↓ to run [calib_camera_pose.py](src_main/calib_camera_pose/calib_camera_pose.py) for calibration:  
> $ roslaunch scan3d_by_baxter calib_camera_pose.launch  

Use ↓ to start the 3D scanner:  
> $ roslaunch scan3d_by_baxter main_3d_scanner.launch 

Details of calibration is described in the "Algorithm" section.

The workflow of the main 3 nodes are described below.

## 2.2. Node1: Move Baxter
file: [src_main/n1_move_baxter.py](src_main/n1_move_baxter.py)

The node controls Baxter to move to several positions in order to take pictures of object from different views.  After Baxter reaches the next goal pose, publish a message of depth_camera's pose to node 2.

Input: (a) [config/T_arm_to_depth.txt](config/T_arm_to_depth.txt); (b) Hard-coded Baxter poses.

Publish: Message to node 2.

## 2.3. Node2: Filter cloud

file: [src_main/n2_filt_and_seg_object.cpp](src_main/n2_filt_and_seg_object.cpp)

The node subscribes the (a) original point cloud, (b) rotated it to the Baxter's frame, (c) filter and segment the cloud to remove points that are noises or far away from the object. The result is then published to node 3.

Subscribe: (a) Message from node 1. (b) Point cloud from depth camera.

Publish: (b) Rotated cloud to rviz. (c) Segmented cloud to node 3.

Meanwhile, it also saves the (a) orignal cloud and (c) segmented cloud to the [data/data/](data/data/) folder. 

## 2.4. Node3: Register clouds
file: [src_main/n3_register_clouds_to_object.py](src_main/n3_register_clouds_to_object.py)

This node subsribes the segmented cloud (which contains the object) from node2. Then it does a registration to obtain the complete 3D model of the object. Finally, the result is saved to file.

Subscribe: Segmented cloud from node2.

Publish: Registration result to rviz.

## 2.5. Fake node1 for debug
file: [src_main/n1_fake_data_publisher.cpp](src_main/n1_fake_data_publisher.cpp)

This is a replacement for "n1_move_baxter.py" and is used for debug. It reads the Baxter poses and point cloud from file, and publishes them to node 2. Thus, I can test previously saved data, and debug without connecting to any hardware.

# 3. Algorithms

## 3.1. Calibrate poses of chessboard and depth_camera

**Locate chessboard**:  

Detect chessboard corners in the image by Harris. Obtain and refine these corners' position (u,v). Since the corners are also in chessboard frame with a coord value of (x=i, y=j, z=0), we can solve this PnP problem and get the relative pose between chessboard and camera frame. (The above operations are achieved in Python using OpenCV library.)

Chessboard has a grid size of 7x9. Let 7 side be X-axis, and 9 be Y-axis. Now there are 4 possible chessboard frames. 

I do 2 things to obtain a unique chessboard frame: 
* Let Z-axis of chessboard pointing to the camera.  
* Manually draw a red circle in the middle of grid on one quadrant of the chessboard. Check which of the 2 quadrants has this red circle by thresholding HSV. Then, I can get a unique coordinate.

Also, I draw the obtained chessboard coordinate onto the 2D image and display it for easier debug.

**Transform Pose to Baxter Frame**:  
Poses of Baxter's frames can be read from '/tf' topic (forward kinematics).  
* For Baxter left hand camera, it already has a frame in the tf tree. 
* For the Depth camera, I placed it on the tf frame of '/left_lower_forearm'.  

With some geometrical computation, I can know where the depth_camera and chessboard is in Baxter frame.

**Procedures of calibration:**  
Face the depth_camera and Baxter left hand camera towards the chessboard. The program reads the '/camera_info' topic, detect and locate the chessboard, and draw out the detected coordinate and xyz-axis. If the detection is good, I'll press a key 'd' and obtain the calibration result, which is then saved to [/config](config) folder.

Main functions are defined in [lib_cam_calib.py](src_python/lib_cam_calib.py) and [lib_geo_trans.py](src_python/lib_geo_trans.py).

## 3.2. Filter point cloud

After acquiring the point cloud, I do following processes (by using PCL's library): 
* Filter by voxel grid and outlier removal.
* Rotate cloud to the Baxter/chessboard coordinate.
* Range filtering: remove points 35cm away from chessboard center.
* Remove the table surface by detecting a plane near z=0 .

Functions are declared in [pcl_filters.h](include/my_pcl/pcl_filters.h) and [pcl_advanced.h](include/my_pcl/pcl_advanced.h).

## 3.3. Registration

Do a [global registration](http://www.open3d.org/docs/tutorial/Advanced/fast_global_registration.html) and an [ICP registration](http://www.open3d.org/docs/tutorial/Basic/icp_registration.html). Then, I use a range filter to retain only the target object.

The colored ICP was not used, because the light changes as robot arm moves to different locations, which makes the color different. 

Functions are defined in [lib_cloud_registration.py](src_python/lib_cloud_registration.py).

# 4. File Structure

[launch/](launch)    
  Launch files, including scripts for starting **my 3D scanner** and **debug and test files**. All my ROS nodes have at least one corresponding launch file stored here.

[config/](config): configuration files: 
  * ".rviz" settings
  * calibration result of chessboard pose and depth_camera pose.  
   (Configrations of algorithm params are set in launch file.)

[include/](include): c++ header files. Mainly wrapped up PCL filters.

[src_cpp/](src_cpp): c++ function definitions.

[src_python/](src_python): Python functions.  Test cases are also included in each script.

[src_main/](src_main)  
Main scripts for this 3D scan project.
* Scripts for 3 main ROS nodes.
* Calibration
* Other assistive nodes.

[test/](test): Testing cpp functions.

[test_ros/](test_ros): Testing ROS scripts, including:
* Read point cloud file and publish to ROS topic by both PCL/open3D.
* Subscribe ROS point cloud and display by both PCL/open3D.




# 5. Dependencies and Installation
Below are the dependencies. Some I give the installing instructions. Others please refer to their official website.  
In short: Eigen, PCL, Open3D, OpenCV(Python) and other ROS packages.

-  Eigen 3  
http://eigen.tuxfamily.org/index.php?title=Main_Page  
$ sudo apt-get install libeigen3-dev   
(Eigen only has header files. No ".so" or ".a".)

-  pcl 1.7  
   > $ sudo add-apt-repository ppa:v-launchpad-jochen-sprickerhof-de/pcl  
   > $ sudo apt-get update  
   > $ sudo apt-get install libpcl-all  

-  pcl_ros  
http://wiki.ros.org/pcl_ros  
   > $ sudo apt-get install ros-melodic-pcl-ros  
   > $ sudo apt-get install   
   > $ ros-melodic-pcl-conversions    

   (The above two might already been installed.)  

-  Open3D  
Two official installation tutorials: [this](http://www.open3d.org/docs/getting_started.html) and [this](http://www.open3d.org/docs/compilation.html).

-  Baxter's packages  
Please follow the long tutorial on [Rethink Robotics' website](http://sdk.rethinkrobotics.com/wiki/Hello_Baxter)


-  OpenCV (C++)
OpenCV >= 3.0  
I used it for some cv::Mat operations.
This is really nice tutorial for install OpenCV 4.0: [link](https://www.pyimagesearch.com/2018/08/15/how-to-install-opencv-4-on-ubuntu/).

-  Some other libs that might be usefll  
   * octomap  
     > $ sudo apt-get install doxygen # a denpendency of octomap  
     > $ sudo apt install octovis # for octomap visualization  
     
     After install above dependencies, clone from https://github.com/OctoMap/octomap, and then "make install" it.  

# 6. Problems to Solve
The current implementation has following problems:
1. Bottom of the object cannot be scanned. 
2. Some part of the object may not be scanned due to occulation of itself.
3. Need additional objects to assist the scan.
4. The accuracy needs improvement.
5. Need intelligent trajectory of the robot arm to scan the object.

# 7. Reference

* A 3d scanner project from last NWU MSR cohort:  
 https://github.com/zjudmd1015/Mini-3D-Scanner.  
It's a really good example for me to get started. Algorithms I used for point cloud processing are almost the same as this.

* PCL and Open3D.  
My codes for the algorithms are basically copied piece by piece from their official tutorial examples.

* https://github.com/karaage0703/open3d_ros  
I referenced this github repo for point_cloud datatype  between open3d and ros. It's useful for me to understand the ROS PointCloud2 datatype, but its code and documentation does have some limitations. Acutually I rewrote the related functions. See this [Github Repo](https://github.com/felixchenfy/open3d_ros_pointcloud_conversion).

