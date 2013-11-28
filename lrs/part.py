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
# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
#from PyQt4.QtGui import *
from qgis.core import *

from utils import *
from error import *

# calibration record
class LrsRecord:
    def __init__(self, milestoneFrom, milestoneTo, partFrom, partTo):
        # measures from mileston measure attribute
        self.milestoneFrom = milestoneFrom
        self.milestoneTo = milestoneTo
        # measures measured along part polyline
        self.partFrom = partFrom
        self.partTo = partTo

    # returns true if measure is within open interval (milestoneFrom,milestoneTo)
    # i.e. milestoneFrom < measure < milestoneTo
    def measureWithin(self, measure):
        return self.milestoneFrom < measure < self.milestoneTo

    # returns true if measure at least partialy overlaps with another record
    def measureOverlaps(self, record ):
        if self.measureWithin( record.milestoneFrom ): return True
        if self.measureWithin( record.milestoneTo ): return True
        if record.measureWithin( self.milestoneFrom ): return True
        if record.measureWithin( self.milestoneTo ): return True
        if record.measureWithin( (self.milestoneFrom+self.milestoneTo)/2 ): return True
        return False

    # get distance from part beginning
    def partMeasure(self, measure):
        md = self.milestoneTo - self.milestoneFrom
        pd = self.partTo - self.partFrom
        k = ( measure - self.milestoneFrom ) / md
        return self.partFrom + k * pd

class LrsSegment:

    def __init__(self, routeId, record, geo ):
        self.routeId = routeId
        self.record = record # LrsRecord
        self.geo = geo # QgsGeometry

# Chain of connected geometries
class LrsRoutePart:

    def __init__(self, polyline, routeId, origins):
        #debug ('init route part' )
        self.polyline = polyline
        self.routeId = routeId
        self.origins = origins # list of LrsOrigin
        self.milestones = [] # LrsMilestone list, all input milestones
        self.records = [] # LrsRecord list
        self.errors = [] # LrsError list

    def calibrate(self):
        polylineGeo = QgsGeometry.fromPolyline( self.polyline ) 

        if len ( self.milestones ) < 2:
            self.errors.append( LrsError( LrsError.NOT_ENOUGH_MILESTONES, polylineGeo, routeId = self.routeId, origins = self.origins ))
            return

        # create list of milestones sorted by partMeasure
        milestones = list ( self.milestones )
        # sort by partMeasure and measure
        milestones.sort ( key=lambda milestone: ( milestone.partMeasure, milestone.measure) )

        # find direction
        up = down = 0
        for i in range( len(milestones)-1 ):
            if milestones[i].measure == milestones[i+1].measure:
                # Could also be reported as error, but should not harm
                pass
            elif milestones[i].measure < milestones[i+1].measure:
                up += 1
            else:
                down += 1

        if up == down:
            self.errors.append( LrsError( LrsError.DIRECTION_GUESS, polylineGeo, routeId = self.routeId, origins = self.origins  ))
            return
        elif down > up: # revert
            self.polyline.reverse()
            milestones.reverse()
            # recalc partMeasures
            length = polylineGeo.length()
            for milestone in milestones:
                milestone.partMeasure = length - milestone.partMeasure

        # remove milestones in wrong direction, to do it well is not trivial because
        # sequence of milestones in correct order may appear in wrong place, e.g.7,8,3,4
        # or it may happen that correct sequence is interrupted by wrong milestone but in
        # correct order respect to longest sequence e.g. 1,2,0,3,4,5
        # Algorithm: 
        #     While there are milestones in wrong order:
        #         * for each milestones calculate correctness score
        #         * mark as error all milestones with lowest score
         
        while True:
            done = True

            # calculate scores
            # score: number of milestones to which it is in correct order minus 
            #        number of milestones to which it is in wrong order,
            #        if both have the same measure, it is considered wrong order
            scores = []

            for i in range(len(milestones)):
                score = 0
                for j in range(len(milestones)):
                    if i == j: continue
                    mi = milestones[i].measure
                    mj = milestones[j].measure
                    if (i < j and mi < mj) or (i > j and mi > mj ):
                        score += 1
                    else:
                        score -= 1 # includes equal measures
                        done = False # at least one in wron order

                scores.append( score )

            if done: break # all in crorrect order

            # find lowest score
            minScore = sys.maxint
            for i in range(len(scores)):
                if scores[i] < minScore: minScore = scores[i]

            # mark all with lowest score as errors, if more neighbours have the same score
            # e.g. measures: 3,0,4,5, both 3 and 0 have score +1, both are marked as 
            # error because we cannot decide which is correct
            for i in range(len(milestones)-1,-1,-1):
                if scores[i] == minScore:
                    m = milestones[i]
                    geo = QgsGeometry.fromPoint( m.pnt )
                    origin = LrsOrigin( QGis.Point, m.fid, m.geoPart, m.nGeoParts )
                    self.errors.append( LrsError( LrsError.WRONG_MEASURE, geo, routeId = self.routeId, measure = m.measure, origins = [ origin ] ))
                    del  milestones[i]

        self.goodMilestones = milestones
        
        # create calibrarion table 
        for i in range(len(milestones)-1):
            m1 = milestones[i]
            m2 = milestones[i+1]
            self.records.append ( LrsRecord ( m1.measure, m2.measure, m1.partMeasure, m2.partMeasure ) )

    def getRecords(self):
        return self.records

    def removeRecord(self, record):
        self.records.remove( record )

    def getRecordGeometry(self, record):
        polyline = polylineSegment( self.polyline, record.partFrom, record.partTo )
        geo = QgsGeometry.fromPolyline( polyline )
        return geo

    def getSegments(self):
        segments = []
        for record in self.records:
            geo = self.getRecordGeometry( record )
            segments.append ( LrsSegment( self.routeId, record, geo ) )
        return segments

    def getErrors(self):
        return self.errors

    def getPoint(self, partMeasure):
        self.polyline

    # returns ( geometry, error )
    def eventGeometry(self, start, end, linear):
        for record in self.records:
            if record.measureWithin( start ):
                m = record.partMeasure( start )
                point = polylinePoint ( self.polyline, m )
                geo = QgsGeometry.fromPoint( point )
                return geo, None

        return None, 'measure not available'

