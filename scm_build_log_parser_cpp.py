import os
import re
import sys
import xml
import yaml
import ntpath
from pathlib import Path
from xml.dom import minidom
import subprocess

temp_dict = {}
num = 23
progFiles = r"C:\program files"
ending_with_dll_reg = re.compile(r'.dll$')

cregex = re.compile(r'^([A-Z|a-z|0-9|\-|_| ]+)(\.c|\.C)$',re.IGNORECASE)
cppregex = re.compile(r'^([A-Z|a-z|0-9|\-|_| ]+)(\.cpp|\.CPP|)$',re.IGNORECASE)
odlregex = re.compile(r'^([A-Z|a-z|0-9|\-|_| ]+)(\.odl|\.ODL)$',re.IGNORECASE)

includefileregex = re.compile(r'Note: including file:')

MS_SYSTEM_REGEX = re.compile(r'externals_replctd\\ms_system\\ms_sdk',re.IGNORECASE)
MS_SYSTEM_ROUGE_REGEX = re.compile(r'externals_replctd\\rogue wave',re.IGNORECASE)
MS_SYSTEM_BOOST_REGEX = re.compile(r'externals_replctd\\boost',re.IGNORECASE)

project_location = re.compile('^Project')
project_location_vcxproj = re.compile(r'\.vcxproj')
project_location_on_node = re.compile('on node 1')
project_location_is_building = re.compile(r'(\([0-9]+:[0-9]+\)|\([0-9]+\)) is building ')

warning_message_text = re.compile('warning MSB8012: TargetPath')
done_building = re.compile('^Done Building Project')
deliverable_name = re.compile('^\s+')
file_path = re.compile(r'(["])(?:(?=(\\?))\2.)*?\1')
lib_regex = re.compile(r'\.lib')
count = 0
same_file_parsing = False
# lib_list = []
# list_sources = []
temp_newdict = {}

#dict_res = {}

def read_library_details(xdom):
    lib_list = []
    item_definition_groups = xdom.getElementsByTagName("ItemDefinitionGroup", )
    for item_definition_group in item_definition_groups:
        condition_value = item_definition_group.attributes['Condition'].value
        if condition_value.find('Release|Win32') != -1:
            links = item_definition_group.getElementsByTagName("Link")
            for link in links:
                add_dep = link.getElementsByTagName("AdditionalDependencies")
                if 0 == len(add_dep):
                    continue
                node = add_dep[0]
                if node.firstChild == None:
                    continue
                text_node = node.firstChild
                text_value = text_node.nodeValue
                lib_list_seperated = text_value.split(';')
                for element in lib_list_seperated:
                    if lib_regex.search(element) and element not in lib_list:
                        element = element.split('.lib')[0]+'.lib'
                        res = element.rsplit(os.sep)[-1]
                        lib_list.append(res)
    #             output_file = link.getElementsByTagName('OutputFile')[0].firstChild.nodeValue
    #             if not '$(TargetName)' in output_file:
    #                 output_file = output_file.split(')')[-1]
    # print("OutPut file "+output_file)
    return lib_list


def find_clr_support(xdom):
    clr_support = ""
    property_groups = xdom.getElementsByTagName("PropertyGroup")
    for property_group in property_groups:
        if property_group.getAttribute('Condition').find("Release|Win32") != -1 and property_group.getAttribute(
                'Label') == "Configuration":
            for child_node in property_group.childNodes:
                if (child_node.nodeName == "CLRSupport"):
                    clr_support = child_node.firstChild.nodeValue
    return clr_support


def get_dll_refernce(xdom, file_name):
    list_of_dll_ref = []
    item_groups = xdom.getElementsByTagName("ItemGroup", )
    for item_group in item_groups:
        Reference_list = item_group.getElementsByTagName("Reference")
        for Reference in Reference_list:
            reference_file_name = Reference.attributes["Include"].value
            if (reference_file_name.find("System") == -1):  # ignore system references
                for child_node in Reference.childNodes:
                    if (child_node.nodeName == "HintPath"):  # TBD - if the path shows "c:\program files..." - ignore
                        str = os.path.abspath(child_node.firstChild.nodeValue)
                        project_path = Path(file_name).parent
                        abs_path = project_path.joinpath(child_node.firstChild.nodeValue)
                        resolved_path = os.path.abspath(abs_path).split(':')[-1]
                        list_of_dll_ref.append(resolved_path)
    return list_of_dll_ref


def get_list_of_proj_dep(xdom, file_name):
    list_of_proj_dep = []
    item_groups = xdom.getElementsByTagName("ItemGroup", )
    for item_group in item_groups:
        Reference_list = item_group.getElementsByTagName("ProjectReference")
        for Reference in Reference_list:
            reference_project_name = Reference.attributes["Include"].value
            if (reference_project_name.find("vcxproj") == -1):  # ignore vcxproj references
                project_path = Path(file_name).parent
                abs_path = project_path.joinpath(reference_project_name)
                resolved_path = os.path.abspath(abs_path).split(':')[-1]
                list_of_proj_dep.append(resolved_path)
    return list_of_proj_dep


def read_source_files_fromvxcproj(xdom, file_name, clr_support_enabled):
    list_sources = []
    dict_res = {}
    dict_idl = {}
    list_path_res = []
    list_idl_dep = []
    global rc_file_rel_path
    rc_file_rel_path = None
    item_groups = xdom.getElementsByTagName("ItemGroup", )
    for item_group in item_groups:
        ClCompile_list = item_group.getElementsByTagName("ClCompile")
        for ClCompile in ClCompile_list:
            is_include_present = False
            ExcludedFromBuild_List = ClCompile.getElementsByTagName("ExcludedFromBuild")
            if ExcludedFromBuild_List:
                for ExcludedFromBuild in ExcludedFromBuild_List:
                    condition_value1 = ExcludedFromBuild.attributes["Condition"].value
                    if condition_value1.find('Release|Win32') != -1:
                        text_node1 = ExcludedFromBuild.firstChild
                        text_value1 = text_node1.nodeValue
                        if (text_value1 == "true"):
                            is_include_present = True
                            break
                        else:
                            is_include_present = False
                            break
                        source_file_name = ClCompile.attributes["Include"].value
                        # print(ClCompile_file_name)
                    else:
                        is_include_present = True
            else:
                source_file_name = ClCompile.attributes["Include"].value
                # print(ClCompile_file_name)
            if is_include_present == False:
                project_path = Path(file_name).parent
                abs_path = project_path.joinpath(source_file_name)
                resolved_path = os.path.abspath(abs_path).split(':')[-1]
                list_sources.append(resolved_path)
        # print(source_file_name)
        Mild_list = item_group.getElementsByTagName("Midl")
        for Midl in Mild_list:
            is_midl_present = False
            ExcludedFromBuild_List = Midl.getElementsByTagName("ExcludedFromBuild")
            if ExcludedFromBuild_List:
                for ExcludedFromBuild in ExcludedFromBuild_List:
                    condition_value1 = ExcludedFromBuild.attributes["Condition"].value
                    if condition_value1.find('Release|Win32') != -1:
                        text_node1 = ExcludedFromBuild.firstChild
                        text_value1 = text_node1.nodeValue
                        if (text_value1 == "true"):
                            is_midl_present = True
                            break
                        else:
                            is_midl_present = False
                            break
                        Midl_file_name = Midl.attributes["Include"].value
                        # print(Midl_file_name)
                    else:
                        is_midl_present = True
            else:
                Midl_file_name = Midl.attributes["Include"].value
                # print(Midl_file_name)
            if is_midl_present == False:
                dict_idl = {}
                project_path = Path(file_name).parent
                abs_path = project_path.joinpath(Midl_file_name)
                org_file_path = os.path.abspath(abs_path)
                list_idl_dep = get_list_of_additionaldep_list(xdom,file_name)
                dict_idl = track_idl_files(xdom,org_file_path,list_idl_dep)
                if dict_idl:
                   for x in list(dict_idl.keys()):
                        if dict_idl[x]['include'] == []:
                            del dict_idl[x]
                resolved_path = os.path.abspath(abs_path).split(':')[-1]
                list_sources.append(resolved_path)
        # print(Midl_file_name)
        ResourceCompile_list = item_group.getElementsByTagName("ResourceCompile")
        #print(ResourceCompile_list)
        for ResourceCompile in ResourceCompile_list:
            ResourceCompile_file_name = ResourceCompile.attributes["Include"].value
            project_path = Path(file_name).parent
            abs_path = project_path.joinpath(ResourceCompile_file_name)
            #This code is to get resource file  path from additional include directory(i.e baselocation of rc files)
            Additional_dir_list  = item_group.getElementsByTagName("AdditionalIncludeDirectories")
            for dir_list in Additional_dir_list:
                condition_value1 = dir_list.attributes["Condition"].value
                if condition_value1.find('Release|Win32') != -1:
                    text_node1 = dir_list.firstChild
                    text_value1 = text_node1.nodeValue
                    if (text_value1.startswith('%(AdditionalIncludeDirectories)')):
                        continue
                    text_value1 = text_value1.split(';')[0]
                    rc_file_rel_path = text_value1
            #Get resource path from additional include directoriees from itemdefinitiongroup
            list_path_res = GetlistofResource_filepath(xdom, file_name)
            dict_res = {}
            if not os.path.exists(abs_path):
                head ,file_act_name = os.path.split(abs_path)
                for item in list_path_res:
                    dir_name =  Path(item)
                    drive,path_of_file =  os.path.splitdrive(file_name)
                    rel_path_name = os.path.join(drive,dir_name,file_act_name)
                    com_path = rel_path_name
                    if os.path.exists(com_path):
                        abs_path = com_path
                        break
            #This function is to add resource file as a key value pair in the source.yaml
            dict_res = track_rc_file(abs_path,rc_file_rel_path,list_path_res)
            if dict_res:
                   for x in list(dict_res.keys()):
                        if dict_res[x]['include'] == []:
                            del dict_res[x]
            global file_rel_path
            global initial_file_name
            file_rel_path = None
            initial_file_name= None
            rc_file_rel_path = None
            resolved_path = os.path.abspath(abs_path).split(':')[-1]
            list_sources.append(resolved_path)
            
        Image_list = item_group.getElementsByTagName("Image")
        for Image in Image_list:
            Image_file_name = Image.attributes["Include"].value
            project_path = Path(file_name).parent
            abs_path = project_path.joinpath(Image_file_name)
            resolved_path = os.path.abspath(abs_path).split(':')[-1]
            list_sources.append(resolved_path)
            
        None_list = item_group.getElementsByTagName("None")
        for None_Inc in None_list:
            None_file_name = None_Inc.attributes["Include"].value
            project_path = Path(file_name).parent
            abs_path = project_path.joinpath(None_file_name)
            resolved_path = os.path.abspath(abs_path).split(':')[-1]
            list_sources.append(resolved_path)

        CustomBuildStep_list = item_group.getElementsByTagName("CustomBuildStep")
        for CustomBuildStep in CustomBuildStep_list:
            iscustomblock_to_write = False
            CustomBuildStep_file_name = CustomBuildStep.attributes["Include"].value
            extension = os.path.splitext(str(CustomBuildStep_file_name).split(os.path.sep)[-1])[1]
            if extension == '.h':
                continue
            ExcludedFromBuild_List = CustomBuildStep.getElementsByTagName("ExcludedFromBuild")
            if ExcludedFromBuild_List:
                for ExcludedFromBuild in ExcludedFromBuild_List:
                    condition_value1 = ExcludedFromBuild.attributes["Condition"].value
                    if condition_value1.find('Release|Win32') != -1:
                        text_node1 = ExcludedFromBuild.firstChild
                        text_value1 = text_node1.nodeValue
                        if text_value1 == "true":
                            iscustomblock_to_write = True
                            break
                        else:
                            iscustomblock_to_write = False
                            break
                        CustomBuildStep_file_name = CustomBuildStep.attributes["Include"].value
                        #print(CustomBuildStep_file_name)
                    else:
                        iscustomblock_to_write = True
            else:
                CustomBuildStep_file_name = CustomBuildStep.attributes["Include"].value
                #print(CustomBuildStep_file_name)
            if iscustomblock_to_write == False:
                project_path = Path(file_name).parent
                abs_path = project_path.joinpath(CustomBuildStep_file_name)
                resolved_path = os.path.abspath(abs_path).split(':')[-1]
                list_sources.append(resolved_path)

        if clr_support_enabled:
            ClCompile_list = item_group.getElementsByTagName("Compile")
            for ClCompile in ClCompile_list:
                source_file_name = ClCompile.attributes["Include"].value
                project_path = Path(file_name).parent
                abs_path = project_path.joinpath(source_file_name)
                resolved_path = os.path.abspath(abs_path).split(':')[-1]
                list_sources.append(resolved_path)
            ClInclude_list = item_group.getElementsByTagName("EmbeddedResource")
            for ClInclude in ClInclude_list:
                ClInclude_file_name = ClInclude.attributes["Include"].value
                project_path = Path(file_name).parent
                abs_path = project_path.joinpath(ClInclude_file_name)
                resolved_path = os.path.abspath(abs_path).split(':')[-1]
                list_sources.append(resolved_path)

    return list_sources,dict_res,dict_idl


#rc_list = []
file_rel_path = None
initial_file_name = None
befor_abs_path = None
def track_rc_file(file_name,check_rel_path_rc2, list_res_path):
    rc_list = []
    fileptr = open(file_name,"r")
    Lines = fileptr.readlines()
    #Adding all the childs to a list and travsersing
    for line in Lines:
        if line.startswith('#include'):
            split_count = len(line.split(" "))
            if split_count > 2:
                list_split = line.split(" ")
                headername = list_split[1]
            else:   
                headername = line.split(" ")[-1]
            rc_list.append(headername)
    org_file_path_name = file_name
    str_path_str = file_name.__str__()
    #This part of the code is to keep original file directory name for further use of it.
    if(".." in str_path_str):
        str_path_str = str_path_str.split("..")[0]
        org_file_path_name = Path(str_path_str)
    else:
        org_file_path_name = os.path.dirname(org_file_path_name)
    for ele in rc_list:
                ele = ele.strip()
                ele = ele.strip('"')
                if('<' in ele):
                    ele = ele.replace("<","")
                if('>' in ele):
                    ele = ele.replace(">","")
                if (ele.startswith('afxres')):
                    continue
                file_found = False
                #To add key valur pair for each rc file
                #To check whether element has .. in its paths
                path = None
                abs_path = None
                key_path = None

                if(len(ele.split('\\'))<=1):
                        str_path = file_name.__str__()
                        if(".." in str_path):
                            head = str_path.split('..')[0]
                            tail = str_path.split('..')[1]
                            global file_rel_path
                            file_rel_path = head
                            global initial_file_name
                            global befor_abs_path
                            befor_abs_path = file_name
                            file_name = os.path.abspath(Path(file_name))
                            initial_file_name = file_name

                        drive,path = os.path.splitdrive(file_name)
                        abs_path = os.path.join(path,ele)
                        key_path = os.path.dirname(os.path.abspath(file_name))
                else:
                        #if the element has path like \res\blockext.rc then use the below logic
                        drive,path = os.path.splitdrive(file_name)
                        com_path = os.path.dirname(os.path.abspath(file_name))
                        abs_path = os.path.join(com_path,ele)
                        key_path = os.path.dirname(os.path.abspath(file_name))
                #This three condition is to check whether the file is present in actual path or additional include directories or original file location.
                if path not in dict_res.keys():
                            path = os.path.join(key_path,ele)
                            path = os.path.abspath(path)
                            drive,path = os.path.splitdrive(os.path.abspath(file_name))
                            dict_res[path] = {'include': []}
                            
                if (path in dict_res.keys()) and (abs_path not in dict_res.values()):
                                com_path = os.path.dirname(os.path.abspath(file_name))
                                abs_path = os.path.join(com_path,ele)
                                str_path_check = abs_path.__str__()
                                if(".." in str_path_check):
                                    abs_path_check = os.path.abspath(Path(str_path_check))
                                    drive , abs_path_check = os.path.splitdrive(abs_path_check)
                                    dict_res[path]['include'].append(abs_path_check)
                                    file_found = True
                                else:
                                    
                                    if(os.path.exists(abs_path)):
                                        drive , abs_path = os.path.splitdrive(abs_path)
                                        dict_res[path]['include'].append(abs_path)
                                        file_found = True
                                    if(file_found == False):
                                        org_file_path = org_file_path_name
                                        if check_rel_path_rc2!=None:
                                            if(".." in check_rel_path_rc2):
                                                rel_path_name = os.path.join(org_file_path,check_rel_path_rc2,ele)
                                            else:
                                                rel_path_name = os.path.join(org_file_path,ele)
                                        else:
                                            rel_path_name = rel_path_name = os.path.join(org_file_path,ele)
                                        rel_path_name = os.path.abspath(rel_path_name)
                                        if(os.path.exists(rel_path_name)):
                                            drive,rel_path_name = os.path.splitdrive(rel_path_name)
                                            dict_res[path]['include'].append(rel_path_name)
                                            file_found = True
                                    if(file_found == False):
                                        rel_path_name = None
                                        for item in list_res_path:
                                            dir_name =  Path(item)
                                            drive,path_of_file =  os.path.splitdrive(file_name)
                                            if(".." in item):
                                                rel_path_name = os.path.join(org_file_path,item,ele)
                                            else:
                                                rel_path_name = os.path.join(drive,dir_name,ele)
                                            rel_path_name = os.path.abspath(rel_path_name)
                                            com_path = rel_path_name
                                            if os.path.exists(rel_path_name):
                                                drive,rel_path_name = os.path.splitdrive(rel_path_name)
                                                dict_res[path]['include'].append(rel_path_name)
                                                file_found = True
                                                break
                                            else:
                                                continue
                if file_found == False:
                                    print("File not found ")
                                    print(abs_path)

    #Travserse each file in the list for track rc2 files.
    for ele in rc_list:
        ele = ele.strip()
        ele = ele.strip('"')
        if ele.endswith('.rc2'):
            if(file_rel_path != None):
                    count = len(ele.split("\\"))
                    str_path_name = file_name.__str__()
                    #if part is for resource file having res\resdll.rc and so on
                    if count >=2:
                        before_str = befor_abs_path.__str__()
                        #This part is for resouce file addtional include directoried traversing
                        if(check_rel_path_rc2!=None):
                            dir_name =  Path(file_name)
                            drive,path_of_file =  os.path.splitdrive(dir_name)
                            path_of_dir = os.path.dirname(dir_name)
                            if(len(check_rel_path_rc2.split('\\'))>2):
                                rel_path_name = os.path.join(drive,path_of_dir,ele)
                                com_path = rel_path_name
                            else:
                                file_path = Path(before_str)
                                path_of_dir = os.path.dirname(file_path)
                                path_of_dir  = path_of_dir.split("..")[0]
                                if(".." in check_rel_path_rc2):
                                    path_of_dir = path_of_dir+check_rel_path_rc2
                                com_path = os.path.join(path_of_dir,ele)
                        else:
                            act_path =  Path(initial_file_name)
                            dir_name = os.path.dirname(act_path)
                            com_path = os.path.join(dir_name,ele)
                            if not os.path.exists(com_path):
                                file_path = Path(before_str)
                                path_of_dir = os.path.dirname(file_path)
                                path_of_dir  = path_of_dir.split("..")[0]
                                com_path = os.path.join(path_of_dir,ele)
                    else:
                        #Normal path traversing
                        act_path =  Path(initial_file_name)
                        dir_name = os.path.dirname(act_path)
                        dir_name = Path(dir_name)
                        complete_path = dir_name.joinpath(Path(ele))
                        com_path = os.path.abspath(Path(complete_path))
            else:
                #Normal path traversing
                drive,path = os.path.splitdrive(file_name)
                com_path = os.path.dirname(os.path.abspath(file_name))
                com_path = os.path.join(com_path,ele)
                
            if os.path.exists(com_path):
                track_rc_file(com_path,check_rel_path_rc2,list_res_path)
            else:
                #This part of the code is to traverse all the additional include directories to find file path
                file_found = False
                for item in list_res_path:
                    dir_name =  Path(item)
                    drive,path_of_file =  os.path.splitdrive(file_name)
                    rel_path_name = os.path.join(drive,dir_name,ele)
                    com_path = rel_path_name
                    if os.path.exists(com_path):
                        track_rc_file(com_path,check_rel_path_rc2,list_res_path)
                        file_found = True
                        break
                    else:
                        continue
                if file_found == False:
                    print("File not found "+com_path)
    return dict_res
            


def GetlistofResource_filepath(xdom, file_name_path):
    list_of_path_dep = []
    
    item_definition_groups = xdom.getElementsByTagName("ItemDefinitionGroup", )
    for item_definition_group in item_definition_groups:
        condition_value = item_definition_group.attributes['Condition'].value
        if condition_value.find('Release|Win32') != -1:
            links = item_definition_group.getElementsByTagName("ResourceCompile")
            for link in links:
                    
                    add_dep = link.getElementsByTagName("AdditionalIncludeDirectories")
                    if 0 == len(add_dep):
                        continue
                    node = add_dep[0]
                    text_node = node.firstChild
                    text_value = text_node.nodeValue
                    lib_list_seperated = text_value.split(';')
                    for element in lib_list_seperated:
                        if("%(AdditionalIncludeDirectories)" in element or "($OUTDIR)" in element):
                            continue
                        else:
                            list_of_path_dep.append(element)
            links_rs = item_definition_group.getElementsByTagName("ClCompile")
            for link in links_rs:
                    
                    add_dep = link.getElementsByTagName("AdditionalIncludeDirectories")
                    if 0 == len(add_dep):
                        continue
                    node = add_dep[0]
                    text_node = node.firstChild
                    text_value = text_node.nodeValue
                    lib_list_seperated = text_value.split(';')
                    for element in lib_list_seperated:
                        if("%(AdditionalIncludeDirectories)" in element or "($OUTDIR)" in element or "%(additionalincludedirectories)" in element):
                            continue
                        else:
                            if element not in list_of_path_dep:
                                list_of_path_dep.append(element)

    return list_of_path_dep



def track_idl_files(xdom,file_name,list_idl_dep):
    idl_list = []
    file_found_list = []
    fileptr = open(file_name,"r")
    Lines = fileptr.readlines()
    #Adding all the childs to a list and travsersing
    for line in Lines:
        if line.startswith('import'):
            split_count = len(line.split(" "))
            if split_count > 2:
                list_split = line.split(" ")
                headername = list_split[1]
            else:   
                headername = line.split(" ")[-1]
            idl_list.append(headername)
    if len(idl_list) == 0:
        return 
    for ele in idl_list:
        ele = ele.strip()
        ele = ele.replace('"','')
        ele = ele.replace(';','')
        ele = ele.rstrip('"')
        file_found = False
        drive,path = os.path.splitdrive(file_name)
        com_path = os.path.dirname(os.path.abspath(file_name))
        abs_path = os.path.join(com_path,ele)
        key_path = os.path.dirname(os.path.abspath(file_name))
        if path not in dict_idl.keys():
                path = os.path.join(key_path,ele)
                path = os.path.abspath(path)
                drive,path = os.path.splitdrive(os.path.abspath(file_name))
                dict_idl[path] = {'include': []}
        if (path in dict_idl.keys()) and (abs_path not in dict_idl.values()):
            com_path = os.path.dirname(os.path.abspath(file_name))
            abs_path = os.path.join(com_path,ele)
            str_path_check = abs_path.__str__()
            if(os.path.exists(abs_path)):
                    file_found_list.append(abs_path)
                    abs_path = os.path.abspath(abs_path)
                    drive , abs_path = os.path.splitdrive(abs_path)
                    if(abs_path not in dict_idl[path]['include']):
                        dict_idl[path]['include'].append(abs_path)
                    
                    file_found = True
            if(file_found == False):
                    rel_path_name = None
                    for item in list_idl_dep:
                        dir_name =  Path(item)
                        drive,path_of_file =  os.path.splitdrive(file_name)
                        if(".." in item):
                            rel_path_name = os.path.join(org_file_path,item,ele)
                            rel_path_name = os.path.abspath(rel_path_name)
                        else:
                            rel_path_name = os.path.join(drive,dir_name,ele)
                        rel_path_name = os.path.abspath(rel_path_name)
                        com_path = rel_path_name
                        if os.path.exists(rel_path_name):
                            file_found_list.append(rel_path_name)
                            drive,rel_path_name = os.path.splitdrive(rel_path_name)
                            if(rel_path_name not in dict_idl[path]['include']):
                                dict_idl[path]['include'].append(rel_path_name)
                            file_found = True
                            break
                        else:
                            continue
        if file_found == False:
                print("idl File not found ")
                #print(abs_path)

    for ele in file_found_list:
        track_idl_files(xdom,ele,list_idl_dep)
    
    return dict_idl

def get_list_of_additionaldep_list(xdom,file_name):
    list_of_sep = []
    item_definition_groups = xdom.getElementsByTagName("ItemDefinitionGroup", )
    for item_definition_group in item_definition_groups:
        condition_value = item_definition_group.attributes['Condition'].value
        if condition_value.find('Release|Win32') != -1:
            links = item_definition_group.getElementsByTagName("Midl")
            for link in links:
                    add_dep = link.getElementsByTagName("AdditionalIncludeDirectories")
                    if 0 == len(add_dep):
                        continue
                    node = add_dep[0]
                    text_node = node.firstChild
                    text_value = text_node.nodeValue
                    lib_list_seperated = text_value.split(';')
                    for element in lib_list_seperated:
                        if("%(AdditionalIncludeDirectories)" in element or "($OUTDIR)" in element or "%(additionalincludedirectories)" in element):
                            continue
                        else:
                            if element not in list_of_sep:
                                list_of_sep.append(element)
    return list_of_sep
    

def get_file_details(file_data):
    file_index = file_data[0]
    file_name = file_data[1]
    file_dep_level_at_index = file_data[2]
    return file_index, file_name, file_dep_level_at_index


def calculateLevel(newstring):
    count = 0
    for ele in newstring:
        if ele == " ":
            count += 1
            continue
        else:
            break
    return count


def read_source_files(build_output):
    idx = 0
    file_list = []
    # build_output = open(logPath, "r")
    for x in build_output:
        word_count = len(re.findall(r'\w+', x))
        # only CPP file should be extraxted TBD
        if word_count == 2:
            if cppregex.search(x.lower()) or cregex.search(x.lower()) or odlregex.search(x.lower()):
                filedata = [idx, x.strip(), 0]
                file_list.insert(idx, filedata)
                idx += 1
        if includefileregex.search(x):
            if progFiles.lower() in x.lower() or ending_with_dll_reg.search(x.lower().strip()):
                continue
            # print(x)
            # TBD to use regex
            x = x[num:]
            levelofcurrentfile = calculateLevel(x)
            x = x.split(':')[-1]
            x = os.path.abspath(x.strip()).split(':')[-1]
            filedata = [idx, x, levelofcurrentfile]
            file_list.insert(idx, filedata)
            idx += 1
    # print(file_list)
    return file_list


def buildDependency(file_list, file_dep_name,drive_name):
    list_externals = []
    finalDict = {}
    immediateParentList = []
    stack = []
    ext_key = 'externals'
    # print(file_list)
    for element in file_list:
        already_present = False
        added_to_final_dict = False
        fileIndex, fileName, fileLevel = get_file_details(element)
        difference = fileLevel - len(immediateParentList)
        if difference > 0:
            try:
                immediateParentList.extend(([immediateParentList[-1]]) * difference)
            except:
                #print(file_list)
                print(element, fileIndex, fileName, fileLevel)
                # print(immediateParentList)
                #print(immediateParentList)

        immediateParentList.insert(fileLevel, fileName)
        immediateParentList = immediateParentList[:fileLevel + 1]

        if fileLevel != 0:
            if not (MS_SYSTEM_REGEX.search(fileName.lower()) or  MS_SYSTEM_ROUGE_REGEX.search(fileName.lower()) or  MS_SYSTEM_BOOST_REGEX.search(fileName.lower())):
                # print('In IF')
                for key in finalDict.keys():
                    # print(immediateParentList)
                    if immediateParentList[fileLevel - 1].lower() == key.lower():
                        for file in finalDict[key]['include']:
                            if fileName.lower() == file.lower():
                                already_present = True
                                added_to_final_dict = True
                                break
                        if not already_present:
                            #check whether the file is present in clean view and proceed
                            org_path = os.path.join(drive_name,fileName)
                            if(os.path.exists(org_path)):
                                finalDict[key]['include'].append(fileName)
                                added_to_final_dict = True
                                break
                if not added_to_final_dict:
                    #check whether the file is present in clean view and proceed
                    org_path = os.path.join(drive_name,fileName)
                    if(os.path.exists(org_path)):
                        finalDict[immediateParentList[fileLevel - 1]] = {'include': []}
                        finalDict[immediateParentList[fileLevel - 1]]['include'].append(fileName)
            else:
                if MS_SYSTEM_REGEX.search(fileName.lower()):
                    ms_sys_val = "ms_sdk"
                    if ms_sys_val not in list_externals:
                        list_externals.append(ms_sys_val)
                        #print(list_externals)
                if MS_SYSTEM_BOOST_REGEX.search(fileName.lower()):
                    ms_sys_val = "boost"
                    if ms_sys_val not in list_externals:
                        list_externals.append(ms_sys_val)
                        #print(list_externals)
                elif MS_SYSTEM_ROUGE_REGEX.search(fileName.lower()):
                    ms_sys_val = "stingray"
                    if ms_sys_val not in list_externals:
                        list_externals.append(ms_sys_val)
                        #print(list_externals)
               
    return (finalDict,list_externals)


def dump_yaml(output_dict_data, output_file):
    stream = open(output_file, 'w')
    yaml.dump(output_dict_data, stream, default_flow_style=False)


def build_list_of_deliverables(log_file_path):
    list_of_deliverables = []
    log_file_contents = open(log_file_path, 'r').read().splitlines()

    # print(log_file_contents)
    line_index = 0
    build_stack = []
    is_vcxproj = False

    while line_index < len(log_file_contents) - 1:
        line = log_file_contents[line_index]

        if project_location.search(line) and project_location_vcxproj.search(line) and project_location_on_node.search(
                line) and not project_location_is_building.search(line):
            build_stack = []
            vcxproj_name = line.split('on node 1')[0].split('Project')[-1].strip()
            vcxproj_name_line = line
            build_stack.append(vcxproj_name)
            start_index = line_index
            is_vcxproj = True

        if project_location.search(line) and project_location_on_node.search(
                line) and project_location_is_building.search(line) and is_vcxproj:
            vcxproj_name = line.split('on node 1')[0].split('is building')[-1].strip()
            build_stack.append(vcxproj_name)
            start_index = line_index

        if done_building.search(line) and is_vcxproj:  # and project_location_vcxproj.search(line):
            build_stack.pop()
            if len(build_stack) > 0:
                start_index = line_index
            else:
                end_index = line_index
                output_list = log_file_contents[start_index + 1:end_index + 1]
                output_list.insert(0, vcxproj_name_line)
                list_of_deliverables.append(output_list)
                is_vcxproj = False

        line_index += 1
    return list_of_deliverables

dict_res = {}
dict_idl = {}
def main():
    list_of_deliverables = ""
    directory = 'with_include'
    make_file_path = ""
    folder_path = ""
    file_name = ""
    output_file = ""
    output_loc = r'c:\temp'
    output_dir = r''

    log_file_path = ""
    if '-p' in sys.argv:
        directory = sys.argv[sys.argv.index('-p') + 1]
    
    if '-o' in sys.argv:
        output_dir = sys.argv[sys.argv.index('-o') + 1]

    #Check whether folder is given as input in command prompt
    path_of_deliverables = os.path.join(output_loc, output_dir)
    if not os.path.isdir(path_of_deliverables):
        os.mkdir(path_of_deliverables)

    log_files = []

    for root, dirs, files in os.walk(directory):
        for filename in files:
            log_files.append(os.path.join(root, filename))

    overall_total = 0
    overall_failed = 0
    drive_name = None
    is_clean_view = True
    for file in log_files:
        if is_clean_view == False:
            break
        print('Processing : ' + file + '==========================================================')
        list_of_deliverables = build_list_of_deliverables(file)
        project_number = 0
        failed_project = 0
        for element in list_of_deliverables:
            file_list = read_source_files(element)
            output_dict = {}
            temp_newdict = {}
            dict_res = {}
            dict_idl = {}
            is_warning = False
            for line in element:
                if project_location.search(line):
                    file_name = file_path.search(line).group().replace('"', '')
                    drive_name,path_of_org_file = os.path.splitdrive(file_name)
                    make_file_path = file_name[2:]
                    folder_path = os.sep.join(make_file_path.split('.')[0].split(os.sep)[:-1])
                    output_file = make_file_path.split('\\')[-1]
                if re.search(warning_message_text, line):
                    is_warning = True
                    data_entry = re.findall('\((.*?)\)', line)
                if re.search(r'^\s+{0}'.format(output_file), line, re.IGNORECASE):
                    output_file = line.split('->')[-1].split('\\')[-1]
                    break
            file_head, file_tail = os.path.splitext(output_file)
            if(".vcxproj" == file_tail ):
                continue
            if is_warning == True:
                output_file = data_entry[3]
                output_file = output_file.split('\\')[-1]  
            #check whether the view is clean and then proceed for further file processing    
            if(drive_name!=None and is_clean_view == True):
                args = ['pushd', drive_name, '&&', 'cleartool'] + ['lsprivate']
                cmd = subprocess.run(args, capture_output=True, text=True, shell=True,)
                try:
                    cmd.check_returncode()
                    nmap_lines = cmd.stdout.splitlines()
                    if(len(nmap_lines)>0):
                        print("Error : selected view is not clean, it contains private files. Execute this python script in a clean view")
                        is_clean_view = False
                        break
                    else:
                        is_clean_view = True
                except subprocess.CalledProcessError:
                    error_message = cmd.stderr.rstrip().split('\n')
                    if len(error_message) == 1:
                        error_message = error_message[0]
                        print(error_message)
                        is_clean_view = False
                        break
                
            
            finalDict , list_ext = buildDependency(file_list, file_name,drive_name)
            # print(finalDict)
            try:
                #print(file_name)
                xdom = xml.dom.minidom.parse(file_name)
                clr_support = find_clr_support(xdom)
                clr_support_values = ['true', 'safe', 'pure']
                list_of_dll_ref = []
                list_of_proj_dep = []
                clr_support_enabled = False
                if clr_support.lower() in clr_support_values:
                    clr_support_enabled = True
                    list_of_dll_ref = get_dll_refernce(xdom, file_name)
                    list_of_proj_dep = get_list_of_proj_dep(xdom, file_name)
                lib_list = read_library_details(xdom)
                
                dict_res.clear()
                dict_idl.clear()
                list_sources, dict_res,dict_idl = read_source_files_fromvxcproj(xdom, file_name, clr_support_enabled)
                output_dict.update({output_file: dict(makefile=make_file_path,
                                                      folder=folder_path,
                                                      clr_support=clr_support,
                                                      libraries=lib_list,
                                                      source=list_sources,
                                                      reference=list_of_dll_ref,
                                                      project_reference=list_of_proj_dep,
                                                      externals = list_ext)})
                for p_id, p_info in finalDict.items():
                    if cppregex.search(p_id) or cregex.search(p_id) or odlregex.search(p_id):
                        for content in list_sources:
                            res_1 = Path(content).parts[-1]
                            if (p_id == res_1):
                                content = os.path.abspath(Path(Path(file_name).parent).joinpath(content)).split(':')[-1]
                                temp_newdict[content] = finalDict[p_id]
                                break
                    else:
                        temp_newdict[p_id] = finalDict[p_id]
                file_seperatore = output_file.split('.')
                if len(file_seperatore) > 2:
                    folder_tobe_created = ".".join(file_seperatore)
                else:
                    folder_tobe_created = output_file  # .split('.')[0]
                path_of_project = os.path.join(path_of_deliverables, folder_tobe_created)
                if not os.path.isdir(path_of_project):
                    os.mkdir(path_of_project)
                temp_newdict.update(dict_res)
                if dict_idl:
                    temp_newdict.update(dict_idl)
                dict_res.clear()
                if dict_idl:
                    dict_idl.clear()
                dump_yaml(temp_newdict, os.path.join(path_of_project, 'source_files.yml'))
                dump_yaml(output_dict, os.path.join(path_of_project, 'deliverables.yml'))

                project_number += 1
                print(str(project_number) + ' > ======= Processing : ' + file_name + ' > ' + path_of_project)
            except Exception as e:
                print(e)
                project_number += 1
                failed_project += 1
                global file_rel_path
                global initial_file_name
                global rc_file_rel_path
                file_rel_path = None
                initial_file_name= None
                rc_file_rel_path = None
                print(
                    str(project_number) + ' > <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Failed Processing : ' + file_name + '>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>')

        overall_total += project_number
        overall_failed += failed_project
        print('Total Projects : ' + str(project_number))
        print(
            '==========================================================DONE Processing==========================================================')

    print(
        '==========================================================Overall Report==========================================================')
    print('| Overall Total Projects : ' + str(overall_total))
    print('| Failed Projects        : ' + str(overall_failed))
    print('| Passed Projects        : ' + str(overall_total - overall_failed))
    print(
        '==================================================================================================================================')


if __name__ == '__main__':
    main()

