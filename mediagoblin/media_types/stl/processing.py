# GNU MediaGoblin -- federated, autonomous media hosting
# Copyright (C) 2011, 2012 MediaGoblin contributors.  See AUTHORS.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import json
import logging
import subprocess
import pkg_resources

from mediagoblin import mg_globals as mgg
from mediagoblin.processing import create_pub_filepath, \
    FilenameBuilder

from mediagoblin.media_types.stl import model_loader


_log = logging.getLogger(__name__)
SUPPORTED_FILETYPES = ['stl', 'obj']

SLIC3R = "/home/felipe/devel/Slic3r/slic3r.pl"

BLEND_FILE = pkg_resources.resource_filename(
    'mediagoblin.media_types.stl',
    os.path.join(
        'assets',
        'blender_render.blend'))
BLEND_SCRIPT = pkg_resources.resource_filename(
    'mediagoblin.media_types.stl',
    os.path.join(
        'assets',
        'blender_render.py'))


def sniff_handler(media_file, **kw):
    if kw.get('media') is not None:
        name, ext = os.path.splitext(kw['media'].filename)
        clean_ext = ext[1:].lower()
    
        if clean_ext in SUPPORTED_FILETYPES:
            _log.info('Found file extension in supported filetypes')
            return True
        else:
            _log.debug('Media present, extension not found in {0}'.format(
                    SUPPORTED_FILETYPES))
    else:
        _log.warning('Need additional information (keyword argument \'media\')'
                     ' to be able to handle sniffing')

    return False

#The GCodeEstimator class is a based on code from Pronsole.py, part of Printrun
# https://github.com/kliment/Printrun
import math
import time

class GCodeEstimator():
  def __init__(self, filename):
    self.gcode = [line.strip() for line in open(filename).readlines()]

  def totalelength(self, g):
      tot=0
      cur=0
      for i in g:
          if "E" in i and ("G1" in i or "G0" in i):
              try:
                  cur=float(i.split("E")[1].split(" ")[0])
              except:
                  pass
          elif "G92" in i and "E0" in i:
              tot+=cur
      return tot

  def get_coordinate_value(self, axis, parts):
      for i in parts:
          if (axis in i):
              return float(i[1:])
      return None

  def hypot3d(self, X1, Y1, Z1, X2=0.0, Y2=0.0, Z2=0.0): 
      return math.hypot(X2-X1, math.hypot(Y2-Y1, Z2-Z1))

  def estimate(self):
      lastx = lasty = lastz = laste = lastf = 0.0
      x = y = z = e = f = 0.0
      currenttravel = 0.0
      totaltravel = 0.0
      moveduration = 0.0
      totalduration = 0.0
      acceleration = 1500.0 #mm/s/s  ASSUMING THE DEFAULT FROM SPRINTER !!!!
      layerduration = 0.0
      layerbeginduration = 0.0
      layercount=0
      #TODO:
      # get device caps from firmware: max speed, acceleration/axis (including extruder)
      # calculate the maximum move duration accounting for above ;)
      # print ".... estimating ...."
      for i in self.gcode:
          i=i.split(";")[0]
          if "G4" in i or "G1" in i:
              if "G4" in i:
                  parts = i.split(" ")
                  moveduration = self.get_coordinate_value("P", parts[1:])
                  if moveduration is None:
                      continue
                  else:
                      moveduration /= 1000.0
              if "G1" in i:
                  parts = i.split(" ")
                  x = self.get_coordinate_value("X", parts[1:])
                  if x is None: x=lastx
                  y = self.get_coordinate_value("Y", parts[1:])
                  if y is None: y=lasty
                  z = self.get_coordinate_value("Z", parts[1:])
                  if z is None: z=lastz
                  e = self.get_coordinate_value("E", parts[1:])
                  if e is None: e=laste
                  f = self.get_coordinate_value("F", parts[1:])
                  if f is None: f=lastf
                  else: f /= 60.0 # mm/s vs mm/m
                  
                  # given last feedrate and current feedrate calculate the distance needed to achieve current feedrate.
                  # if travel is longer than req'd distance, then subtract distance to achieve full speed, and add the time it took to get there.
                  # then calculate the time taken to complete the remaining distance

                  currenttravel = self.hypot3d(x, y, z, lastx, lasty, lastz)
                  distance = 2* ((lastf+f) * (f-lastf) * 0.5 ) / acceleration  #2x because we have to accelerate and decelerate
                  if distance <= currenttravel and ( lastf + f )!=0 and f!=0:
                      moveduration = 2 * distance / ( lastf + f )
                      currenttravel -= distance
                      moveduration += currenttravel/f
                  else:
                      moveduration = math.sqrt( 2 * distance / acceleration )

              totalduration += moveduration

              if z > lastz:
                  layercount +=1
                  #print "layer z: ", lastz, " will take: ", time.strftime('%H:%M:%S', time.gmtime(totalduration-layerbeginduration))
                  layerbeginduration = totalduration

              lastx = x
              lasty = y
              lastz = z
              laste = e
              lastf = f

      return (layercount, totalduration)

def blender_render(config):
    """
    Called to prerender a model.
    """
    arg_string = "blender -b blender_render.blend -F "
    arg_string +="JPEG -P blender_render.py"
    env = {"RENDER_SETUP" : json.dumps(config), "DISPLAY":":0"}
    subprocess.call(
        ["blender",
         "-b", BLEND_FILE,
         "-F", "JPEG",
         "-P", BLEND_SCRIPT],
        env=env)

def slicer(input_filename, output_file, fill_density=0.4, filament_diameter=2.8, layer_height=0.25):
    subpr = subprocess.Popen(
        [SLIC3R, input_filename,
          "--output", output_file,
          "--nozzle-diameter", "0.35",
          "--print-center", "100,100",
          "--gcode-flavor", "reprap",
          "--use-relative-e-distances",
          "--filament-diameter", str(filament_diameter),
          "--extrusion-multiplier", "1",
          "--temperature", "185",
          "--bed-temperature", "60",
          "--travel-speed", "130",
          "--perimeter-speed", "30",
          "--small-perimeter-speed", "30",
          "--external-perimeter-speed", "70%",
          "--infill-speed", "80",
          "--solid-infill-speed", "60",
          "--top-solid-infill-speed", "50",
          "--support-material-speed", "60",
          "--bridge-speed", "60",
          "--gap-fill-speed", "20",
          "--first-layer-speed", "30%",
          "--perimeter-acceleration", "0",
          "--infill-acceleration", "0",
          "--bridge-acceleration", "0",
          "--default-acceleration", "130",
          "--layer-height", str(layer_height),
          "--first-layer-height", "100%",
          "--infill-every-layers", "1",
          "--solid-infill-every-layers", "0",
          "--perimeters", "3",
          "--top-solid-layers", "3",
          "--bottom-solid-layers", "3",
          "--fill-density", str(fill_density),
          "--fill-angle", "45",
          "--fill-pattern", "rectilinear",
          "--solid-fill-pattern", "rectilinear",
          "--extra-perimeters", "yes",
          "--randomize-start", "yes",
          "--avoid-crossing-perimeters", "no",
          "--external-perimeters-first", "no",
          "--only-retract-when-crossing-perimeters", "yes",
          "--solid-infill-below-area", "70",
          "--infill-only-where-needed", "no",
          "--infill-first", "no",
          "--retract-length", "1",
          "--retract-speed", "30",
          "--retract-restart-extra", "0",
          "--retract-before-travel", "2",
          "--retract-lift", "0",
          "--retract-layer-change", "yes",
          "--scale", "1",
          "--rotate", "0",
          "--duplicate", "1",
          "--bed-size", "200,200",
          "--duplicate-grid", "1,1",
          "--duplicate-distance", "6",
#          "--start-gcode", "'G28 X Y'",
          "--resolution", "0"], stdout=subprocess.PIPE)

    filament_length = 0
    plastic_volume = 0
    for line in subpr.stdout:
        if "Filament required" in line.rstrip():
            filament_length = line.rstrip().split("required: ")[1].split("mm (")[0]
            plastic_volume = line.rstrip().split("mm (")[1].split("cm3)")[0]

    return (filament_length, plastic_volume)

def process_stl(proc_state):
    """Code to process an stl or obj model. Will be run by celery.

    A Workbench() represents a local tempory dir. It is automatically
    cleaned up when this function exits.
    """
    entry = proc_state.entry
    workbench = proc_state.workbench

    queued_filepath = entry.queued_media_file
    queued_filename = workbench.localized_file(
        mgg.queue_store, queued_filepath, 'source')
    name_builder = FilenameBuilder(queued_filename)

    ext = queued_filename.lower().strip()[-4:]
    if ext.startswith("."):
        ext = ext[1:]
    else:
        ext = None

    # Attempt to parse the model file and divine some useful
    # information about it.
    with open(queued_filename, 'rb') as model_file:
        model = model_loader.auto_detect(model_file, ext)

    # generate preview images
    greatest = [model.width, model.height, model.depth]
    greatest.sort()
    greatest = greatest[-1]

    def generate_gcode(input_filename, output_filename):
        """
        Called to slice the model and generate a gcode file.
        """
        filename = name_builder.fill(output_filename)
        output_file = workbench.joinpath(filename)

        filament_length, plastic_volume = slicer(input_filename, output_file, fill_density=0.4, filament_diameter=2.8, layer_height=0.25)
        layer_count, total_duration = GCodeEstimator(output_file).estimate()

        # make sure the image rendered to the workbench path
        assert os.path.exists(output_file)

        # copy it up!
        with open(output_file, 'rb') as gcode:
            public_path = create_pub_filepath(entry, filename)

            with mgg.public_store.get_file(public_path, "wb") as public_file:
                public_file.write(gcode.read())

        return (public_path, filament_length, plastic_volume, layer_count, total_duration)

    def snap(name, camera, width=640, height=640, project="ORTHO"):
        filename = name_builder.fill(name)
        workbench_path = workbench.joinpath(filename)
        shot = {
            "model_path": queued_filename,
            "model_ext": ext,
            "camera_coord": camera,
            "camera_focus": model.average,
            "camera_clip": greatest*10,
            "greatest": greatest,
            "projection": project,
            "width": width,
            "height": height,
            "out_file": workbench_path,
            }
        blender_render(shot)

        # make sure the image rendered to the workbench path
        assert os.path.exists(workbench_path)

        # copy it up!
        with open(workbench_path, 'rb') as rendered_file:
            public_path = create_pub_filepath(entry, filename)

            with mgg.public_store.get_file(public_path, "wb") as public_file:
                public_file.write(rendered_file.read())

        return public_path

    blender_thumbs = True
    try:
      thumb_path = snap(
          "{basename}.thumb.jpg",
          [0, greatest*-1.5, greatest],
          mgg.global_config['media:thumb']['max_width'],
          mgg.global_config['media:thumb']['max_height'],
          project="PERSP")

      perspective_path = snap(
          "{basename}.perspective.jpg",
          [0, greatest*-1.5, greatest], project="PERSP")

      topview_path = snap(
          "{basename}.top.jpg",
          [model.average[0], model.average[1], greatest*2])

      frontview_path = snap(
          "{basename}.front.jpg",
          [model.average[0], greatest*-2, model.average[2]])

      sideview_path = snap(
          "{basename}.side.jpg",
          [greatest*-2, model.average[1], model.average[2]])
    except:
      blender_thumbs = False
      pass

    gcode_filepath, filament_length, plastic_volume, layer_count, total_duration = generate_gcode(queued_filename, '{basename}.gcode')

    ## Save the public file stuffs
    model_filepath = create_pub_filepath(
        entry, name_builder.fill('{basename}{ext}'))

    with mgg.public_store.get_file(model_filepath, 'wb') as model_file:
        with open(queued_filename, 'rb') as queued_file:
            model_file.write(queued_file.read())

    # Remove queued media file from storage and database
    mgg.queue_store.delete_file(queued_filepath)
    entry.queued_media_file = []

    # Insert media file information into database
    media_files_dict = entry.setdefault('media_files', {})
    media_files_dict[u'original'] = model_filepath
    media_files_dict[u'gcode'] = gcode_filepath
    if blender_thumbs:
      media_files_dict[u'thumb'] = thumb_path
      media_files_dict[u'perspective'] = perspective_path
      media_files_dict[u'top'] = topview_path
      media_files_dict[u'side'] = sideview_path
      media_files_dict[u'front'] = frontview_path

    # Put model dimensions into the database
    dimensions = {
        "center_x" : model.average[0],
        "center_y" : model.average[1],
        "center_z" : model.average[2],
        "width" : model.width,
        "height" : model.height,
        "depth" : model.depth,
        "filament_length": filament_length,
        "plastic_volume": plastic_volume,
        "layer_count": layer_count, 
        "total_duration": total_duration,
        "file_type" : ext,
        "blender_thumbs" : blender_thumbs,
        }
    entry.media_data_init(**dimensions)
