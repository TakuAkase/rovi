#include <ros/ros.h>
#include <std_srvs/Trigger.h>
#include <sensor_msgs/PointCloud.h>
#include <sensor_msgs/PointCloud2.h>
#include <sensor_msgs/point_cloud_conversion.h>
#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.h>
#include "rovi/Floats.h"
#include "rovi/GenPC.h"
#include "ps_main.h"
#include <stdio.h>

bool isready = false;

ros::NodeHandle *nh;
ros::Publisher *pub1, *pub3;

std::vector<double> vecQ;

// Phase Shift method calc parameters
PS_PARAMS param =
{
  .search_div = PH_SEARCH_DIV,
  .bw_diff = BW_DIFF,
  .brightness = BRIGHTNESS,
  .darkness = DARKNESS,
  .step_diff = STEP_DIFF,
  .reject_diff = REJECT_DIFF,
  .max_ph_diff = MAX_PH_DIFF,
  .max_parallax = MAX_PARALLAX,
  .min_parallax = MIN_PARALLAX,
  .rdup_cnt = RIGHT_DUP_N,
  .ls_points = LS_POINTS,
  .evec_error = EVEC_ERROR,
};

int reload(){
  nh->getParam("pshift_genpc/calc/search_div", param.search_div);
  nh->getParam("pshift_genpc/calc/bw_diff", param.bw_diff);
  nh->getParam("pshift_genpc/calc/brightness", param.brightness);
  nh->getParam("pshift_genpc/calc/darkness", param.darkness);
  nh->getParam("pshift_genpc/calc/step_diff", param.step_diff);
  nh->getParam("pshift_genpc/calc/reject_diff", param.reject_diff);
  nh->getParam("pshift_genpc/calc/max_ph_diff", param.max_ph_diff);
  nh->getParam("pshift_genpc/calc/max_parallax", param.max_parallax);
  nh->getParam("pshift_genpc/calc/min_parallax", param.min_parallax);
  nh->getParam("pshift_genpc/calc/rdup_cnt", param.rdup_cnt);
  nh->getParam("pshift_genpc/calc/ls_points", param.ls_points);

  nh->getParam("genpc/Q", vecQ); 
  if (vecQ.size() != 16){
    ROS_ERROR("Param Q NG");
    return -1;
  }
  ROS_INFO("genpc:reload ok");
  return 0;
}

bool genpc(rovi::GenPC::Request &req, rovi::GenPC::Response &res){
  ROS_INFO("genpc called: %d %d", req.imgL.size(), req.imgR.size());

  if (!isready) {
    int width = req.imgL[0].width;
    int height = req.imgL[0].height;
    ROS_INFO("genpc img w, h: %d %d", width, height);
    ps_init(width, height);
    ROS_INFO("ps_init done");
    isready=true;
  }
  reload();
  ps_setparams(param);

  // read Phase Shift data images. (13 left images and 13 right images)
  try
  {
    for (int j = 0; j < 13; j++)
    {
      cv::Mat img = cv_bridge::toCvCopy(req.imgL[j], sensor_msgs::image_encodings::MONO8)->image;
      ps_setpict(0, j, img);
      cv::imwrite(cv::format("/tmp/capt%02d_0.pgm", j), img);
      img = cv_bridge::toCvCopy(req.imgR[j], sensor_msgs::image_encodings::MONO8)->image;
      ps_setpict(1, j, img);
      cv::imwrite(cv::format("/tmp/capt%02d_1.pgm", j), img);
    }
    FILE *f=fopen("/tmp/captseq.log","w");
    for(int j=0;j<13;j++){
      fprintf(f,"(%d) %d %d\n",j,req.imgL[j].header.seq,req.imgR[j].header.seq);
    }
    fclose(f);
  }
  catch (cv_bridge::Exception& e)
  {
    ROS_ERROR("genpc:cv_bridge:exception: %s", e.what());
    return false;
  }

  // do calc
  ROS_INFO("before ps_exec");
  Eigen::MatrixXd &diff = ps_exec();
  Eigen::Matrix4d Q;
  ROS_INFO("before memcpy");
  memcpy(Q.data(), vecQ.data(), sizeof(double) * 4 * 4);
  ROS_INFO("before genPC");
  int N = genPC(diff, ps.texture, ps.mask[0], ps.pt, Q);
  ROS_INFO("genPC returned N=%d", N);

  // output point clouds
  sensor_msgs::PointCloud pts;
  pts.header.stamp = ros::Time::now();
  pts.header.frame_id = "/camera";
  pts.points.resize(N);
  pts.channels.resize(3);
  pts.channels[0].name = "r";
  pts.channels[0].values.resize(N);
  pts.channels[1].name = "g";
  pts.channels[1].values.resize(N);
  pts.channels[2].name = "b";
  pts.channels[2].values.resize(N);
  rovi::Floats buf;
  buf.data.resize(3*N);
  for (int n = 0; n < N; n++)
  {
    int n3=3*n;
    buf.data[n3++]=pts.points[n].x = _pcd[n].coord[0];
    buf.data[n3++]=pts.points[n].y = _pcd[n].coord[1];
    buf.data[n3]=pts.points[n].z = _pcd[n].coord[2];
    pts.channels[0].values[n] = _pcd[n].col[0] / 255.0;
    pts.channels[1].values[n] = _pcd[n].col[1] / 255.0;
    pts.channels[2].values[n] = _pcd[n].col[2] / 255.0;
    if (n < 20 || (N - 20) < n)
    {
      ROS_INFO("n=%d x,y,z=%f,%f,%f r,g,b=%f,%f,%f",
        n,
        pts.points[n].x,
        pts.points[n].y,
        pts.points[n].z,
        pts.channels[0].values[n],
        pts.channels[1].values[n],
        pts.channels[2].values[n]
      );
    }
  }

  ROS_INFO("before outPLY");
  outPLY("/tmp/test.ply");
  outPLY("/tmp/testRG.ply", RANGE_GRID);
  ROS_INFO("after  outPLY");

  pub1->publish(pts);
  pub3->publish(buf);

  res.pc_cnt = N;

  ROS_INFO("now return");
  return true;
}

int main(int argc, char **argv){
  ros::init(argc, argv, "genpc_node");
  ros::NodeHandle n;
  nh = &n;
  if(reload()<0) return 1;

  ros::ServiceServer svc1 = n.advertiseService("genpc", genpc);
  ros::Publisher p1 = n.advertise<sensor_msgs::PointCloud>("ps_pc", 1);
  pub1 = &p1;
  ros::Publisher p3 = n.advertise<rovi::Floats>("ps_floats", 1);
  pub3 = &p3;
  ros::spin();
  return 0;
}
