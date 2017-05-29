import numpy as np
import cv2

OBSTACLE_COLOR_INDEX = 0
ROCK_COLOR_INDEX = 1
GROUND_COLOR_INDEX = 2

# Identify pixels above the threshold
# Threshold of RGB > 160 does a nice job of identifying ground pixels only
def color_thresh(img, rgb_thresh=(160, 160, 160)):
    # Create an array of zeros same size as img
    color_select = np.zeros_like(img)
    
    # Require that each pixel be above all three threshold values in RGB
    # above_thresh will now contain a boolean array with "True"
    # where threshold was met
    above_thresh = (img[:,:,0] > rgb_thresh[0]) \
                & (img[:,:,1] > rgb_thresh[1]) \
                & (img[:,:,2] > rgb_thresh[2])
    
    # Invisible triangle areas under warped view can't be assumed to be obstacles, so we look for non-zero obstacle pixels
    obstacle_thresh = (0 < img[:,:,0]) & (img[:,:,0] <= rgb_thresh[0]) \
                & (0 < img[:,:,1]) & (img[:,:,1] <= rgb_thresh[1]) \
                & (0 < img[:,:,2]) & (img[:,:,2] <= rgb_thresh[2])
            
    rock_thresh = (img[:,:,0] > 100) & (img[:,:,1] > 100) & (img[:,:,2] < 75)
    
    # Index the array of zeros with the boolean array and set to 1
    color_select[:,:,OBSTACLE_COLOR_INDEX][obstacle_thresh] = 1
    color_select[:,:,ROCK_COLOR_INDEX][rock_thresh] = 1
    color_select[:,:,GROUND_COLOR_INDEX][above_thresh] = 1
    # Return the binary image
    return color_select

# Define a function to convert to rover-centric coordinates
def rover_coords(binary_img):
    # Identify nonzero pixels
    ypos, xpos = binary_img.nonzero()
    # Calculate pixel positions with reference to the rover position being at the 
    # center bottom of the image.  
    x_pixel = np.absolute(ypos - binary_img.shape[0]).astype(np.float)
    y_pixel = -(xpos - binary_img.shape[0]).astype(np.float)
    return x_pixel, y_pixel


# Define a function to convert to radial coords in rover space
def to_polar_coords(x_pixel, y_pixel):
    # Convert (x_pixel, y_pixel) to (distance, angle) 
    # in polar coordinates in rover space
    # Calculate distance to each pixel
    dist = np.sqrt(x_pixel**2 + y_pixel**2)
    # Calculate angle away from vertical for each pixel
    angles = np.arctan2(y_pixel, x_pixel)
    return dist, angles

# Define a function to apply a rotation to pixel positions
def rotate_pix(xpix, ypix, yaw):
    # Convert yaw to radians
    # Apply a rotation
    yaw_rad = yaw * np.pi / 180
    xpix_rotated = xpix * np.cos(yaw_rad) - ypix * np.sin(yaw_rad)
    ypix_rotated = xpix * np.sin(yaw_rad) + ypix * np.cos(yaw_rad)
    return xpix_rotated, ypix_rotated

# Define a function to perform a translation
def translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale): 
    # Apply a scaling and a translation
    xpix_translated = np.int_(xpos + (xpix_rot / scale))
    ypix_translated = np.int_(ypos + (ypix_rot / scale))
    return xpix_translated, ypix_translated

# Define a function to apply rotation and translation (and clipping)
# Once you define the two functions above this function should work
def pix_to_world(xpix, ypix, xpos, ypos, yaw, world_size, scale):
    # Apply rotation
    xpix_rot, ypix_rot = rotate_pix(xpix, ypix, yaw)
    # Apply translation
    xpix_tran, ypix_tran = translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale)
    # Perform rotation, translation and clipping all at once
    x_pix_world = np.clip(np.int_(xpix_tran), 0, world_size - 1)
    y_pix_world = np.clip(np.int_(ypix_tran), 0, world_size - 1)
    # Return the result
    return x_pix_world, y_pix_world

# Define a function to perform a perspective transform
def perspect_transform(img, src, dst):
           
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (img.shape[1], img.shape[0]))# keep same size as input image
    
    return warped


# Apply the above functions in succession and update the Rover state accordingly
def perception_step(Rover):
    # Perform perception steps to update Rover()
    # NOTE: camera image is coming to you in Rover.img
    img = Rover.img
    
    # 1) Define source and destination points for perspective transform
    dst_size = 5 
    bottom_offset = 6
    source = np.float32([[14, 140], [301 ,140],[200, 96], [118, 96]])
    destination = np.float32([[img.shape[1]/2 - dst_size, img.shape[0] - bottom_offset],
                      [img.shape[1]/2 + dst_size, img.shape[0] - bottom_offset],
                      [img.shape[1]/2 + dst_size, img.shape[0] - 2*dst_size - bottom_offset], 
                      [img.shape[1]/2 - dst_size, img.shape[0] - 2*dst_size - bottom_offset],
                      ])
    
    # 2) Apply perspective transform
    warped = perspect_transform(img, source, destination)
    
    # 3) Apply color threshold to identify navigable terrain/obstacles/rock samples
    warped_thresholded = color_thresh(warped)
    
    # 4) Update Rover.vision_image (this will be displayed on left side of screen)
    #Rover.vision_image = warped
    Rover.vision_image = warped_thresholded * 255 # maximize RGB values of binary mask images otherwise it'll appear too dark since the binary image values are just 1's
    
    # 5) Convert map image pixel values to rover-centric coords
    navigable_xpix, navigable_ypix = rover_coords(warped_thresholded[:,:,GROUND_COLOR_INDEX])
    obstacle_xpix, obstacle_ypix = rover_coords(warped_thresholded[:,:,OBSTACLE_COLOR_INDEX])
    rock_xpix, rock_ypix = rover_coords(warped_thresholded[:,:,ROCK_COLOR_INDEX])
    
    # 6) Convert rover-centric pixel values to world coordinates
    navigable_x_world, navigable_y_world = pix_to_world(navigable_xpix, 
                                                        navigable_ypix, 
                                                        Rover.pos[0], 
                                                        Rover.pos[1], 
                                                        Rover.yaw, 
                                                        world_size=Rover.worldmap.shape[0], 
                                                        scale=10)
    obstacle_x_world, obstacle_y_world = pix_to_world(obstacle_xpix, 
                                                      obstacle_ypix, 
                                                      Rover.pos[0], 
                                                      Rover.pos[1], 
                                                      Rover.yaw, 
                                                      world_size=Rover.worldmap.shape[0], 
                                                      scale=10)
    rock_x_world, rock_y_world = pix_to_world(rock_xpix, 
                                              rock_ypix, 
                                              Rover.pos[0], 
                                              Rover.pos[1], 
                                              Rover.yaw, 
                                              world_size=Rover.worldmap.shape[0],
                                              scale=10)
    
    # 7) Update Rover worldmap (to be displayed on right side of screen)
    angle_tolerance = 0.1 # Map fidelity will be compromised if readings are accepted while vehicle has too much pitch and/or roll
    if (Rover.pitch < angle_tolerance or Rover.pitch > 360.0 - angle_tolerance) and (Rover.roll < angle_tolerance or Rover.roll > 360.0 - angle_tolerance):
        Rover.worldmap[obstacle_y_world, obstacle_x_world, 0] += 1
        Rover.worldmap[rock_y_world, rock_x_world, 1] += 1
        Rover.worldmap[navigable_y_world, navigable_x_world, 2] += 1

    # 8) Convert rover-centric pixel positions to polar coordinates
    # Update Rover pixel distances and angles
    rover_centric_pixel_distances, rover_centric_angles = to_polar_coords(navigable_xpix, navigable_ypix)
    Rover.nav_dists = rover_centric_pixel_distances
    Rover.nav_angles = rover_centric_angles
    
 
    
    
    return Rover