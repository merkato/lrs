# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LrsPlugin
                                 A QGIS plugin
 Linear reference system builder and editor
                              -------------------
        begin                : 2013-10-02
        copyright            : (C) 2013 by Radim Blažek
        email                : radim.blazek@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import sys, math
# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
#from PyQt4.QtGui import *
from qgis.core import *

# name of plugin in project file
PROJECT_PLUGIN_NAME = "lrs"

# print debug message
def debug(msg):
    print "LRS: %s" % msg
    sys.stdout.flush()

# test if two QgsPolyline are identical including reverse order
# return False - not identical
#        True - identical
def polylinesIdentical( polyline1, polyline2 ):
    if polyline1 == polyline2: 
        return True
    
    tmp = []
    tmp.extend(polyline2)
    tmp.reverse()
    return polyline1 == tmp

# return hash of QgsPoint (may be used as key in dictionary)
def pointHash( point ):
    return "%s-%s" % ( point.x().__hash__(), point.y().__hash__() )

def pointsDistance( p1, p2 ):
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return math.sqrt( dx*dx + dy*dy)

def segmentLength( polyline, segment ):
    p1 = polyline[segment]
    p2 = polyline[segment+1]
    return pointsDistance( p1, p2 )

# calculate distance along line to pnt
def measureAlongPolyline( polyline, segment, pnt ):
    measure = 0.0
    for i in range(segment):
        measure += segmentLength( polyline, i )
    
    measure += pointsDistance( polyline[segment], pnt )
    return measure

# delete all features from layer
def clearLayer( layer ):
    if not layer: return

    iterator = layer.getFeatures()
    ids = []
    feature = QgsFeature()
    while iterator.nextFeature(feature): ids.append( feature.id() )

    layer.startEditing()
    for id in ids: layer.deleteFeature( id )
    layer.commitChanges()

# place point on line in distance from point 1
def pointOnLine( point1, point2, distance ):
    dx = point2.x() - point1.x()
    dy = point2.y() - point1.y()
    k = distance / math.sqrt(dx*dx+dy*dy)
    x = point1.x() + k * dx
    y = point1.y() + k * dy
    return QgsPoint( x, y )

# returns new polyline 'from - to' measured along original oplyline
def polylineSegment( polyline, frm, to ):
    geo = QgsGeometry.fromPolyline( polyline )
    length = geo.length()

    poly = [] # section
    length = 0
    for i in range(len(polyline)-1):
        p1 = polyline[i]
        p2 = polyline[i+1]
        l = pointsDistance( p1, p2 )

        if len(poly) == 0 and frm <= length + l:
            d = frm - length
            p = pointOnLine ( p1, p2, d )
            poly.append( p )

        if len(poly) > 0:
            if to < length + l:
                d = to - length
                p = pointOnLine ( p1, p2, d )
                poly.append( p )
                break
            else:
                poly.append( p2 )

        length += l

    return poly

def getLayerFeature( layer, fid ):
    if not layer: return None

    request = QgsFeatureRequest().setFilterFid(fid)

    # StopIteration is raised if fid does not exist
    feature = layer.getFeatures(request).next()

    return feature
    
