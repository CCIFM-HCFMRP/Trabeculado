import os, os.path
import unittest
import vtk, qt, ctk, slicer, numpy
from slicer.ScriptedLoadableModule import *
import logging

# TrabeculadoBatch
class TrabeculadoBatch(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "TrabeculadoBatch"
        self.parent.categories = ["HCFMRP"]
        self.parent.dependencies = []
        self.parent.contributors = ["Julio C Ferranti (CCIFM-FMRP-USP)"]
        self.parent.helpText = """Executa o Trabeculado Osseo em lote, com varios exames."""
        self.parent.helpText += self.getDefaultModuleDocumentationLink()
        self.parent.acknowledgementText = """ """

# TrabeculadoBatchWidget
class TrabeculadoBatchWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Parameters Area
        parametersCollapsibleButton = ctk.ctkCollapsibleButton()
        parametersCollapsibleButton.text = "Parametros"
        self.layout.addWidget(parametersCollapsibleButton)

        # Layout within the dummy collapsible button
        mainFormLayout = qt.QFormLayout(parametersCollapsibleButton)

        # label(mask) value
        self.labelROISpin = qt.QSpinBox()
        self.labelROISpin.setMinimum(0)
        self.labelROISpin.setMaximum(2048)
        self.labelROISpin.setToolTip("Valor do Label (cor) para o ROI.")
        mainFormLayout.addRow("ROI Label Value", self.labelROISpin)

        # label(mask) value
        self.labelCortSpin = qt.QSpinBox()
        self.labelCortSpin.setMinimum(0)
        self.labelCortSpin.setMaximum(2048)
        self.labelCortSpin.setToolTip("valor do Label (cor) para o Osso Cortical")
        mainFormLayout.addRow("Osso Cortical Label Value", self.labelCortSpin)

        # Apply Button
        self.applyButton = qt.QPushButton("Iniciar")
        self.applyButton.toolTip = "Inicie o processamento."
        #self.applyButton.enabled = False
        mainFormLayout.addRow(self.applyButton)

        # Progress Bar
        self.progressBar = qt.QProgressBar()
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setVisible(False)
        mainFormLayout.addRow(self.progressBar)

        self.resultButton = qt.QPushButton("Salvar imagens")
        #self.resultButton.enabled = False
        mainFormLayout.addRow(self.resultButton)

        # Add vertical spacer
        self.layout.addStretch(1)

        # Conexoes
        self.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.resultButton.connect('clicked(bool)', self.onResultButton)

        # Refresh Apply button state
        self.onSelect()

    def cleanup(self):
        pass

    def onSelect(self):
        pass

    def onResultButton(self):
        directory = qt.QFileDialog.getExistingDirectory()

        for node in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode'):
            if 'Result' in node.GetName():
                filename = node.GetName() + ".nii"
                properties = {'useCompression': 0} #do not compress
                filePath = os.path.join(directory, filename)
                slicer.util.saveNode(node, filePath, properties)

    def onApplyButton(self):
        self.applyButton.setText("Aguarde...")
        self.applyButton.setEnabled(False)
        self.progressBar.setVisible(True)
        slicer.app.processEvents()

        # Criar tabela para os dados
        logging.info('Criando a tabela')
        self.table = slicer.vtkMRMLTableNode()
        tableWasModified = self.table.StartModify()
        self.table.SetName("Export Table")
        self.table.SetUseColumnNameAsColumnHeader(True)
        col = self.table.AddColumn(); col.SetName("Volume")
        col = self.table.AddColumn(); col.SetName("ICort")
        col = self.table.AddColumn(); col.SetName("ITrab")
        col = self.table.AddColumn(); col.SetName("Ilow")
        col = self.table.AddColumn(); col.SetName("FVTO")

        for node in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode'):
            if node.GetClassName() == "vtkMRMLLabelMapVolumeNode":
                logging.info('Ignorando label: ' + node.GetName())
                continue
            else:
                logging.info('Processando ' + node.GetName())
                input = node
                label = slicer.util.getNode(node.GetName() + '-label')
                ROILabelValue = self.labelROISpin.value
                cortLabelValue = self.labelCortSpin.value
                self.run(input, label, ROILabelValue, cortLabelValue)

        # Adiciona a tabela a cena e exibe
        logging.info('Adicionar tabela e exibir')
        slicer.mrmlScene.AddNode(self.table)
        slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpTableView)
        slicer.app.applicationLogic().GetSelectionNode().SetReferenceActiveTableID(self.table.GetID())
        slicer.app.applicationLogic().PropagateTableSelection()
        self.table.EndModify(tableWasModified)

        self.applyButton.setText("Iniciar")
        self.applyButton.setEnabled(True)
        return

    def hasImageData(self, volumeNode):
        if not volumeNode:
            logging.debug('Falha em hasImageData: Sem volume')
            return False
        if volumeNode.GetImageData() is None:
            logging.debug('Falha em hasImageData: Volume nao possue dados de imagem')
            return False
        return True

    def isValidInputOutputData(self, inputVolumeNode, outputVolumeNode):
        if not inputVolumeNode:
            logging.debug('Falha em isValidInputOutputData: Volume nao definido')
            return False
        if not outputVolumeNode:
            logging.debug('Falha em isValidInputOutputData: Volume nao definido')
            return False
        if inputVolumeNode.GetID()==outputVolumeNode.GetID():
            logging.debug('Falha em isValidInputOutputData: Volumes de entrada e saida sao os mesmos.')
            return False
        return True

    def run(self, inputVolume, labelMap, ROIValue, cortValue):
        logging.info('Processing started')

        if not self.isValidInputOutputData(inputVolume, labelMap):
            slicer.util.errorDisplay('Volumes de entrada e saida sao so mesmos. Escolha outros volumes')
            return False

        volumeLogic = slicer.modules.volumes.logic()
        slicer.app.processEvents()

        # Executar correcao N4ITK
        self.progressBar.value = 10
        slicer.app.processEvents()
        n4itkVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", inputVolume.GetName() + ' N4ITK')
        parameters = {}
        parameters["inputImageName"] = inputVolume.GetID()
        parameters["outputImageName"] = n4itkVolume.GetID()
        n4itkModule = slicer.modules.n4itkbiasfieldcorrection
        slicer.cli.run(n4itkModule, None, parameters, wait_for_completion=True)
        logging.info('N4ITK finished')

        # Executar CastScalarVolume
        self.progressBar.value = 20
        slicer.app.processEvents()
        castVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", inputVolume.GetName() + ' Cast Volume')
        parameters.clear()
        parameters["InputVolume"] = n4itkVolume.GetID()
        parameters["OutputVolume"] = castVolume.GetID()
        parameters["Type"] = "Int"
        csv = slicer.modules.castscalarvolume
        slicer.cli.run(csv, None, parameters, wait_for_completion=True)
        logging.info('Cast Scalar Volume finished')

        # Inverter voxels do Volume
        self.progressBar.value = 30
        slicer.app.processEvents()
        invertVolume = volumeLogic.CloneVolume(slicer.mrmlScene, castVolume, inputVolume.GetName() + ' Inverted Volume')
        invertVolume.SetName(inputVolume.GetName() + ' Inverted Volume')
        a = slicer.util.array(invertVolume.GetName())
        Max=0
        if (a.max() < 256):                              # 8 bits
            Max=255
        if (a.max() >= 256) and (a.max() < 4096):        # 12 bits
            Max=4095
        if (a.max() >= 4096) and (a.max() < 16384):      # 14 bits
                Max=16383
        if (a.max() >= 16384) and (a.max() < 65536):     # 16 bits
            Max=65535

        a[:] = Max -a                                    #inverte os valores dos voxels
        logging.info('Inverted Volume finished')
        #invertVolume.GetImageData().Modified()

        # Calcular osso cortical
        self.progressBar.value = 40
        slicer.app.processEvents()
        volumeArray = slicer.util.array(invertVolume.GetName())
        labelArray = slicer.util.array(labelMap.GetName())
        points = numpy.where(labelArray == cortValue)
        values = volumeArray[points]
        ICort = values.mean()
        logging.info('Calculo do Osso Cortical (ICort) finished')

        # Calculo da media da ROI (ITrab)
        self.progressBar.value = 50
        slicer.app.processEvents()
        ROIArray = slicer.util.array(invertVolume.GetName())
        labelArray = slicer.util.array(labelMap.GetName())
        points = numpy.where(labelArray == ROIValue)
        values = volumeArray[points]
        ocorrencias = numpy.bincount(values)                   #contar ocorrencias. Posicao e o valor!
        ocorrenciasList = list(ocorrencias)                    #converter array numpy em lista
        ocurrenciasListSorted = numpy.sort(ocorrenciasList)    #ordenar array
        ITrab = values.mean()                                  #media dos pontos
        logging.info('Calculo da ROI (ITrab) finished')

        # capturar o valor do pixel (posicao) no vetor do pico do histograma
        picoPixelValue=ocorrenciasList.index(ocorrencias.max())

        # Encontrar ILow
        if (ocorrencias.max()/2) in ocorrencias:
            ILow=ocorrenciasList.index(ocorrencias.max()/2)
        else:
            for x in ocurrenciasListSorted:
                if x > (ocorrencias.max()/2):
                    posterior=ocorrenciasList.index(x)
                    break
                else:
                    anterior=ocorrenciasList.index(x)
        try:
            ILow
            #print 'ilow existe'
        except NameError:
            #print 'ilow nao existe'
            if (posterior-(ocorrencias.max()/2)) <= ((ocorrencias.max()/2)-anterior):
                ILow = posterior
            else:
                ILow = anterior

        logging.info('Procura ILow finished')

        FVTO = (ITrab - ILow) / (ICort - ILow)
        logging.info('Calculo do FVTO finished')

        # Executa Mask Scalar Volume no ROI
        self.progressBar.value = 60
        slicer.app.processEvents()
        ROIVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", inputVolume.GetName() + ' ROI Volume')
        parameters.clear()
        parameters["InputVolume"] = invertVolume.GetID()
        parameters["MaskVolume"] = labelMap.GetID()
        parameters["OutputVolume"] = ROIVolume.GetID()
        parameters["Label"] = ROIValue
        maskScalarVolume = slicer.modules.maskscalarvolume
        slicer.cli.run(maskScalarVolume, None, parameters, wait_for_completion=True)
        logging.info('Mask Scalar Volume finished')

        # Posicionando a ROI para cortar a imagem
        self.progressBar.value = 70
        slicer.app.processEvents()

        # Achar o centro da imagem segmentada
        array = slicer.util.array(ROIVolume.GetName())
        points = numpy.where(array > 0)

        # Calculo da posicao
        pos = [0.0, 0.0, 0.0]
        IJKtoRASMatrix = vtk.vtkMatrix4x4()
        ROIVolume.GetIJKToRASMatrix(IJKtoRASMatrix)
        i = points[2].max() - (points[2].max() - points[2].min())/2
        j = points[1].max() - (points[1].max() - points[1].min())/2
        k = points[0].max() - (points[0].max() - points[0].min())/2
        IJK = [i, j, k, 1]
        RAS = IJKtoRASMatrix.MultiplyPoint(IJK)
        pos[0] = RAS[0]
        pos[1] = RAS[1]
        pos[2] = RAS[2]

        # Calculo das dimensoes
        spacing = [0.0, 0.0, 0.0]
        spacing = ROIVolume.GetSpacing()
        L = ((points[0].max() - points[0].min())/2*spacing[0])+spacing[0]
        P = ((points[2].max() - points[2].min())/2*spacing[2])+spacing[1]
        A = ((points[1].max() - points[1].min())/2*spacing[1])+spacing[1]
        print L, P, A

        # Criar a ROI
        ROI = slicer.vtkMRMLAnnotationROINode()
        ROI.SetName(inputVolume.GetName() + ' ROI')
        slicer.mrmlScene.AddNode(ROI)
        ROI.SetXYZ(pos)
        ROI.SetRadiusXYZ(L, P, A)
        ROI.SetDisplayVisibility(True)

        # Realiza o Crop da imagem
        #Crop Voxel Based
        self.progressBar.value = 80
        slicer.app.processEvents()
        cropLogic = slicer.modules.cropvolume.logic()
        cropVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", inputVolume.GetName() + ' Cropped Volume')
        parametersNode = slicer.vtkMRMLCropVolumeParametersNode()
        parametersNode.SetInputVolumeNodeID(ROIVolume.GetID())
        parametersNode.SetOutputVolumeNodeID(cropVolume.GetID())
        parametersNode.SetROINodeID(ROI.GetID())
        parametersNode.SetVoxelBased(True)
        slicer.mrmlScene.AddNode(parametersNode)
        cropLogic.SnapROIToVoxelGrid(parametersNode)
        cropLogic.Apply(parametersNode)

        # Binarizar volume
        self.progressBar.value = 90
        slicer.app.processEvents()
        resultVolume = volumeLogic.CloneVolume(slicer.mrmlScene, cropVolume, inputVolume.GetName() + ' Result Volume')
        resultVolume.SetName(inputVolume.GetName() + ' Result Volume')
        arrayResult = slicer.util.array(resultVolume.GetName())
        arrayResult[arrayResult < ITrab] = 0
        arrayResult[arrayResult >= ITrab] = Max
        logging.info('Volume ROI Binario finished')

        # Popular tabela
        logging.info('Popular tabela')
        rowIndex = self.table.AddEmptyRow()
        self.table.SetCellText(rowIndex, 0, inputVolume.GetName())
        self.table.SetCellText(rowIndex, 1, str(ICort))
        self.table.SetCellText(rowIndex, 2, str(ITrab))
        self.table.SetCellText(rowIndex, 3, str(ILow))
        self.table.SetCellText(rowIndex, 4, str(FVTO))

        # Exibir o resultado
        logging.info('Exibir resultado')
        for color in ['Red', 'Yellow', 'Green']:
            slicer.app.layoutManager().sliceWidget(color).sliceLogic().GetSliceCompositeNode().SetBackgroundVolumeID(resultVolume.GetID())

        self.resultButton.enabled = True
        self.progressBar.value = 100
        slicer.app.processEvents()

        logging.info('Processing finished')

        return True

class TrabeculadoBatchTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        self.setUp()
        self.test_TrabeculadoOsseo1()

    def test_TrabeculadoOsseo1(self):
        pass
