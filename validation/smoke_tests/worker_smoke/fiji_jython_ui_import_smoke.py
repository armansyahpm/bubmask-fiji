from ij import IJ
from ij.gui import OvalRoi, Overlay, TextRoi
from java.awt import GridBagConstraints, GridBagLayout, Insets
from java.awt.event import ActionListener, MouseAdapter
from java.io import FileWriter
from javax.swing import ImageIcon, JButton, JCheckBox, JComboBox, JFrame, JLabel, JPanel, JScrollPane, JSlider, JTabbedPane, JTable, JTextArea, JTextField, JToggleButton
from javax.swing.event import ChangeListener


path = "C:\\Users\\arman\\tor_mere\\bubmask-fiji\\validation\\worker_smoke\\fiji_jython_ui_import_smoke.ok"
writer = FileWriter(path)
try:
    writer.write("ok\n")
    writer.write("OvalRoi=" + str(OvalRoi) + "\n")
    writer.write("MouseAdapter=" + str(MouseAdapter) + "\n")
    writer.write("ChangeListener=" + str(ChangeListener) + "\n")
    writer.write("ImageIcon=" + str(ImageIcon) + "\n")
    writer.write("ScrollPane=" + str(JScrollPane) + "\n")
    writer.write("TabbedPane=" + str(JTabbedPane) + "\n")
    writer.write("Table=" + str(JTable) + "\n")
    writer.write("TextArea=" + str(JTextArea) + "\n")
    writer.write("Combo=" + str(JComboBox(["a", "b"]).getSelectedItem()) + "\n")
    writer.write("Text=" + str(JTextField("183.000", 10).getText()) + "\n")
finally:
    writer.close()

IJ.log("BubMask Fiji/Jython UI import smoke passed")
