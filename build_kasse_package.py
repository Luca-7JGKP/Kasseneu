import io
import os
import tarfile
import time

print("--- WoltLab Plugin Builder: V205 (Package + XML Fixes) ---")

def desktop_dir() -> str:
    """Return the user's desktop path across OSes."""
    try:
        return os.path.join(os.environ["USERPROFILE"], "Desktop")
    except KeyError:
        return os.path.join(os.path.expanduser("~"), "Desktop")


desktop = desktop_dir()

# ==========================================================================
# 1. SCSS
# ==========================================================================
scss_content = r"""
.kasse-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px; }
.kasse-card {
    background-color: var(--wcfContentBackground); border: 1px solid var(--wcfContentBorderInner); border-radius: 6px; padding: 20px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    &.highlight { border-top: 4px solid var(--wcfSuccessText); }
    .amount { font-size: 2.2rem; font-weight: 700; margin: 10px 0; color: var(--wcfContentText); }
    .label { text-transform: uppercase; font-size: 0.85rem; color: var(--wcfTextColorDimmed); letter-spacing: 0.5px; }
}
.kasse-sub-stats {
    display: flex; justify-content: space-around; margin-top: 15px; padding-top: 10px; border-top: 1px solid var(--wcfContentBorderInner);
    .fa-paypal { color: #003087; } .fa-building-columns { color: #4b6584; } .fa-wallet { color: #f7b731; }
}
/* Project Progress Bars */
.kasse-project-list {
    margin-top: 30px;
    .kasse-project {
        background: var(--wcfContentBackground); border: 1px solid var(--wcfContentBorderInner); border-radius: 6px; padding: 15px; margin-bottom: 15px;
        h3 { margin-top: 0; font-size: 1.1rem; display: flex; justify-content: space-between; }
        .project-meta { font-size: 0.85rem; color: var(--wcfTextColorDimmed); margin-bottom: 5px; }
        .progress-bar-wrap {
            height: 20px; background: var(--wcfContentBorderInner); border-radius: 10px; overflow: hidden; position: relative;
            .progress-bar { height: 100%; background: var(--wcfSuccessText); transition: width 0.5s ease-in-out; }
            .progress-text { position: absolute; width: 100%; text-align: center; top: 0; line-height: 20px; font-size: 0.75rem; color: #fff; text-shadow: 0 0 2px #000; }
        }
    }
}
.kasse-dropzone {
    border: 2px dashed var(--wcfContentBorderInner); padding: 30px; text-align: center; background: var(--wcfInputBackground);
    border-radius: 6px; cursor: pointer; transition: all 0.2s;
    &:hover { border-color: var(--wcfPrimaryText); }
    input[type=file] { display: none; }
}
@include screen-md-down {
    .kasse-mobile-cards {
        thead { display: none; }
        tr { display: block; margin-bottom: 15px; background: var(--wcfContentBackground); border: 1px solid var(--wcfContentBorderInner); border-radius: 6px; padding: 10px; }
        td { display: flex; justify-content: space-between; border: none; padding: 5px 0; &::before { content: attr(data-label); font-weight: bold; color: var(--wcfTextColorDimmed); } }
    }
}
"""

css_global = ""

# ==========================================================================
# 2. PHP CLASSES
# ==========================================================================

php_helper = r"""<?php
namespace wcf\system\kasse;
use wcf\system\WCF;
class KasseHelper {
    public static function toCents($amountStr) { $amountStr = str_replace(',', '.', $amountStr); return (int) round(floatval($amountStr) * 100); }
    public static function toFloat($cents) { return (float) ($cents / 100); }
    public static function log($action, $details = '') {
        $sql = "INSERT INTO wcf".WCF_N."_wg_audit_log (userID, username, action, details, time) VALUES (?, ?, ?, ?, ?)";
        WCF::getDB()->prepareStatement($sql)->execute([WCF::getUser()->userID??0, WCF::getUser()->username??'System', $action, $details, TIME_NOW]);
    }
    public static function getTreasurers() {
        $sql = "SELECT DISTINCT user_to_group.userID FROM wcf".WCF_N."_user_to_group user_to_group JOIN wcf".WCF_N."_user_group_option_value option_value ON (user_to_group.groupID = option_value.groupID) JOIN wcf".WCF_N."_user_group_option option_def ON (option_value.optionID = option_def.optionID) WHERE option_def.optionName = 'user.profile.kasse.canManage' AND option_value.optionValue = 1";
        try { $stmt = WCF::getDB()->prepareStatement($sql); $stmt->execute(); return $stmt->fetchSingleColumn() ?: []; } catch (\Exception $e) { return []; }
    }
    public static function getCategories() { try { $s=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_category ORDER BY showOrder"); $s->execute(); return $s->fetchAll(); } catch (\Exception $e) { return []; } }
    public static function getAccounts() { try { $s=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_account ORDER BY title"); $s->execute(); return $s->fetchAll(); } catch (\Exception $e) { return []; } }
    public static function getProjects() { try { $s=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_project WHERE status='open' ORDER BY title"); $s->execute(); return $s->fetchAll(); } catch (\Exception $e) { return []; } }
}
"""

php_listener = r"""<?php
namespace wcf\system\event\listener;
use wcf\system\WCF;
class KasseACPOptionListener implements IParameterizedEventListener {
    public function execute($eventObj, $className, $eventName, array &$parameters) {
        if (!isset($eventObj->categoryName) || $eventObj->categoryName !== 'kasse.general') return;
        $checks = [];
        try { $stmt = WCF::getDB()->prepareStatement("SELECT 1 FROM wcf".WCF_N."_wg_transaction LIMIT 1"); $stmt->execute(); $checks['db'] = true; } catch (\Exception $e) { $checks['db'] = false; }
        $dir = WCF_DIR . 'images/kasse/';
        if (!file_exists($dir)) @mkdir($dir, 0777, true);
        $checks['dir'] = is_writable($dir);
        WCF::getTPL()->assign(['kasseChecks' => $checks]);
    }
}
"""

# DBO Classes
php_trans_obj = r"""<?php
namespace wcf\data\kasse\transaction;
use wcf\data\DatabaseObject;
class KasseTransaction extends DatabaseObject { protected static $databaseTableName = 'wg_transaction'; protected static $databaseTableIndexName = 'transactionID'; }
"""
php_trans_list = r"""<?php
namespace wcf\data\kasse\transaction;
use wcf\data\DatabaseObjectList;
class KasseTransactionList extends DatabaseObjectList { public $className = KasseTransaction::class; }
"""
php_proj_obj = r"""<?php
namespace wcf\data\kasse\project;
use wcf\data\DatabaseObject;
class KasseProject extends DatabaseObject { protected static $databaseTableName = 'wg_project'; protected static $databaseTableIndexName = 'projectID'; }
"""
php_proj_list = r"""<?php
namespace wcf\data\kasse\project;
use wcf\data\DatabaseObjectList;
class KasseProjectList extends DatabaseObjectList { public $className = KasseProject::class; }
"""

# Trophy Logic
php_trophy = r"""<?php
namespace wcf\system\user\trophy\criterion;
use wcf\data\user\User;
use wcf\system\WCF;
class KasseContributionCriterion extends AbstractUserTrophyCriterion {
    public function check($value, User $user) {
        if (!$user->userID) return false;
        $sql = "SELECT SUM(amount) FROM wcf".WCF_N."_wg_transaction WHERE userID = ? AND amount > 0";
        $stmt = WCF::getDB()->prepareStatement($sql);
        $stmt->execute([$user->userID]);
        $sumCents = $stmt->fetchSingleColumn();
        $targetCents = (int)($value * 100);
        return $sumCents >= $targetCents;
    }
}
"""

# ACP Pages
php_acp_proj_list = r"""<?php
namespace wcf\acp\page;
use wcf\page\AbstractPage;
use wcf\system\WCF;
class KasseProjectListPage extends AbstractPage {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.projects';
    public function assignVariables() {
        parent::assignVariables();
        $sql = "SELECT * FROM wcf".WCF_N."_wg_project ORDER BY status DESC, title ASC";
        $stmt = WCF::getDB()->prepareStatement($sql);
        $stmt->execute();
        WCF::getTPL()->assign(['projects' => $stmt->fetchAll()]);
    }
}
"""
php_acp_proj_add = r"""<?php
namespace wcf\acp\form;
use wcf\form\AbstractForm;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\acp\page\KasseProjectListPage;
use wcf\system\kasse\KasseHelper;
class KasseProjectAddForm extends AbstractForm {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.projects';
    public function save() {
        parent::save();
        $cents = KasseHelper::toCents($_POST['targetAmount']);
        $sql = "INSERT INTO wcf".WCF_N."_wg_project (title, description, targetAmount, status) VALUES (?, ?, ?, 'open')";
        WCF::getDB()->prepareStatement($sql)->execute([$_POST['title'], $_POST['description'], $cents]);
        $this->saved();
        HeaderUtil::redirect(LinkHandler::getInstance()->getControllerLink(KasseProjectListPage::class));
        exit;
    }
}
"""

# Overview (With Projects)
php_overview = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
class KasseOverviewPage extends AbstractPage {
    public $activeMenuItem = 'de.wildesgebilde.kasse.Overview';
    public function readData() { parent::readData(); if (!WCF::getSession()->getPermission('user.profile.kasse.canUse')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function assignVariables() {
        parent::assignVariables();
        $balances = ['total' => 0.0, 'paypal' => 0.0, 'bank' => 0.0, 'cash' => 0.0];
        try {
            $sql = "SELECT accountType, SUM(amount) as s FROM wcf".WCF_N."_wg_transaction GROUP BY accountType";
            $stmt = WCF::getDB()->prepareStatement($sql); $stmt->execute();
            while($r = $stmt->fetchArray()){ if(isset($balances[$r['accountType']])) { $balances[$r['accountType']] = KasseHelper::toFloat($r['s']); } $balances['total'] += KasseHelper::toFloat($r['s']); }
        } catch(\Exception $e){}

        $projects = [];
        try {
            $sql = "SELECT p.*, (SELECT SUM(amount) FROM wcf".WCF_N."_wg_transaction t WHERE t.projectID = p.projectID) as currentSum FROM wcf".WCF_N."_wg_project p WHERE p.status = 'open'";
            $stmt = WCF::getDB()->prepareStatement($sql);
            $stmt->execute();
            while($row = $stmt->fetchArray()) {
                $row['targetAmount'] = KasseHelper::toFloat($row['targetAmount']);
                $row['currentSum'] = KasseHelper::toFloat($row['currentSum'] ?? 0);
                $row['percent'] = ($row['targetAmount'] > 0) ? min(100, round(($row['currentSum'] / $row['targetAmount']) * 100)) : 0;
                $projects[] = $row;
            }
        } catch(\Exception $e){}

        $myInvoices = [];
        try { $stmt=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_invoice WHERE userID=? AND status IN ('open','pending_approval')"); $stmt->execute([WCF::getUser()->userID]); while($r=$stmt->fetchArray()){ $r['amount']=KasseHelper::toFloat($r['amount']); $myInvoices[]=$r; } } catch(\Exception $e){}
        $isTreasurer = WCF::getSession()->getPermission('user.profile.kasse.canManage');
        $adminPendingInvoices = [];
        if($isTreasurer){ try { $stmt=WCF::getDB()->prepareStatement("SELECT i.*, u.username FROM wcf".WCF_N."_wg_invoice i LEFT JOIN wcf".WCF_N."_user u ON (i.userID = u.userID) WHERE i.status = 'pending_approval'"); $stmt->execute(); while($r=$stmt->fetchArray()){ $r['amount']=KasseHelper::toFloat($r['amount']); $adminPendingInvoices[]=$r; } } catch(\Exception $e){} }

        WCF::getTPL()->assign(['balances' => $balances, 'myInvoices' => $myInvoices, 'isTreasurer' => $isTreasurer, 'adminPendingInvoices' => $adminPendingInvoices, 'projects' => $projects]);
    }
}
"""

php_log = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
use wcf\data\kasse\transaction\KasseTransactionList;
class KasseLogPage extends AbstractPage {
    public $activeMenuItem = 'de.wildesgebilde.kasse.Log';
    public $category = '';
    public function readParameters() { parent::readParameters(); if(isset($_REQUEST['category'])) $this->category = $_REQUEST['category']; }
    public function readData() { parent::readData(); if (!WCF::getSession()->getPermission('user.profile.kasse.canUse')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function assignVariables() {
        parent::assignVariables();
        $list = new KasseTransactionList();
        if(!empty($this->category)) $list->getConditionBuilder()->add('category = ?', [$this->category]);
        $list->sqlOrderBy = 'transactionDate DESC';
        $list->readObjects();
        $entries = [];
        foreach($list as $obj) {
            $row = $obj->getData();
            $row['amount'] = KasseHelper::toFloat($row['amount']);
            $u = \wcf\data\user\User::getUser($row['userID']);
            $row['username'] = $u->username ?? 'System';
            $entries[] = $row;
        }
        WCF::getTPL()->assign(['entries' => $entries, 'filterCategory' => $this->category, 'availableCategories' => KasseHelper::getCategories()]);
    }
}
"""

php_add = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\page\KasseOverviewPage;
use wcf\system\kasse\KasseHelper;
use wcf\system\user\notification\UserNotificationHandler;
use wcf\data\kasse\KasseNotificationObject;
class KasseAddForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public $categories=[];
    public $accounts=[];
    public $projects=[];
    public function readData(){ parent::readData(); $this->categories=KasseHelper::getCategories(); $this->accounts=KasseHelper::getAccounts(); $this->projects=KasseHelper::getProjects(); }
    public function assignVariables(){ parent::assignVariables(); WCF::getTPL()->assign(['categories'=>$this->categories,'accounts'=>$this->accounts, 'projects'=>$this->projects]); }
    public function save(){ parent::save(); $cents=KasseHelper::toCents($_POST['amount']); if($_POST['type']==='expense') $cents=-1*abs($cents); else $cents=abs($cents); $pid = isset($_POST['projectID']) ? intval($_POST['projectID']) : 0; $db=WCF::getDB(); $db->prepareStatement("INSERT INTO wcf".WCF_N."_wg_transaction (transactionDate, creationDate, userID, accountType, amount, category, description, projectID) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")->execute([TIME_NOW, TIME_NOW, WCF::getUser()->userID, $_POST['accountType'], $cents, $_POST['category'], $_POST['description'], $pid]); KasseHelper::log('Buchung gemeldet', KasseHelper::toFloat($cents)); $this->saved(); HeaderUtil::delayedRedirect(LinkHandler::getInstance()->getControllerLink(KasseOverviewPage::class), 2); exit; }
}
"""

# STANDARD FILES (All Definitions)
php_print = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
class KasseInvoicePrintPage extends AbstractPage {
    public $id = 0;
    public function readParameters() { parent::readParameters(); if(isset($_REQUEST['id'])) $this->id = intval($_REQUEST['id']); }
    public function readData() { parent::readData(); if(!$this->id) throw new \wcf\system\exception\IllegalLinkException(); }
    public function assignVariables() {
        parent::assignVariables();
        $sql = "SELECT * FROM wcf".WCF_N."_wg_invoice WHERE invoiceID = ?";
        $stmt = WCF::getDB()->prepareStatement($sql);
        $stmt->execute([$this->id]);
        $invoice = $stmt->fetchArray();
        $invoice['amount'] = KasseHelper::toFloat($invoice['amount']);
        WCF::getTPL()->assign(['invoice' => $invoice, 'printDate' => TIME_NOW]);
    }
}
"""
php_import = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\page\KasseOverviewPage;
use wcf\system\kasse\KasseHelper;
class KasseImportForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function readData() { parent::readData(); if (!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function save() { parent::save(); if (isset($_FILES['csvFile']) && !empty($_FILES['csvFile']['tmp_name'])) { $handle=fopen($_FILES['csvFile']['tmp_name'],"r"); $count=0; while(($data=fgetcsv($handle,1000,";"))!==FALSE){ if(count($data)<2)continue; $count++; } fclose($handle); KasseHelper::log('CSV Import',"$count Zeilen"); } $this->saved(); }
}
"""
php_fee_edit = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\data\user\User;
use wcf\page\KasseMembershipPage;
use wcf\system\kasse\KasseHelper;
use wcf\system\exception\IllegalLinkException;
use wcf\system\exception\PermissionDeniedException;
class KasseUserFeeForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public $userID=0;
    public $user=null;
    public $fee=0.00;
    public function readParameters(){ parent::readParameters(); if(isset($_REQUEST['id'])) $this->userID=intval($_REQUEST['id']); $this->user=new User($this->userID); if(!$this->user->userID) throw new IllegalLinkException(); }
    public function readData(){ parent::readData(); if(!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new PermissionDeniedException(); try{ $stmt=WCF::getDB()->prepareStatement("SELECT fee FROM wcf".WCF_N."_wg_user_fee WHERE userID=?"); $stmt->execute([$this->userID]); $c=$stmt->fetchSingleColumn(); if($c!==false) $this->fee=KasseHelper::toFloat($c); }catch(\Exception $e){} }
    public function assignVariables(){ parent::assignVariables(); WCF::getTPL()->assign(['editUser'=>$this->user, 'currentFee'=>$this->fee]); }
    public function save(){ parent::save(); $cents=KasseHelper::toCents($_POST['amount']); $sql="INSERT INTO wcf".WCF_N."_wg_user_fee (userID, fee) VALUES (?, ?) ON DUPLICATE KEY UPDATE fee = ?"; WCF::getDB()->prepareStatement($sql)->execute([$this->userID, $cents, $cents]); KasseHelper::log('Beitrag geändert', "User: {$this->user->username}, Neu: ".KasseHelper::toFloat($cents)); $this->saved(); HeaderUtil::delayedRedirect(LinkHandler::getInstance()->getControllerLink(KasseMembershipPage::class), 2); exit; }
}
"""
php_fee_run = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\page\KasseOverviewPage;
use wcf\system\kasse\KasseHelper;
use wcf\system\user\notification\UserNotificationHandler;
use wcf\data\kasse\KasseInvoiceNotificationObject;
class KasseFeeForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function readData(){ parent::readData(); if(!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function save(){ parent::save(); $title=$_POST['title']; $db=WCF::getDB(); $sql="SELECT userID FROM wcf".WCF_N."_user"; $stmt=$db->prepareStatement($sql); $stmt->execute(); $count=0; while($row=$stmt->fetchArray()){ $feeCents=0; try{ $f=$db->prepareStatement("SELECT fee FROM wcf".WCF_N."_wg_user_fee WHERE userID=?"); $f->execute([$row['userID']]); $c=$f->fetchSingleColumn(); if($c!==false) $feeCents=(int)$c; }catch(\Exception $e){} if($feeCents>0){ $db->prepareStatement("INSERT INTO wcf".WCF_N."_wg_invoice (userID,title,amount,status,createdTime,recurrence) VALUES (?,?,?, 'open', ?, 'none')")->execute([$row['userID'], $title, $feeCents, TIME_NOW]); $id=$db->getInsertID('wcf'.WCF_N.'_wg_invoice','invoiceID'); try{ $obj=new KasseInvoiceNotificationObject($id); UserNotificationHandler::getInstance()->fireEvent('invoiceCreated','de.wildesgebilde.kasse.invoice',$obj,[$row['userID']]); }catch(\Exception $e){} $count++; } } KasseHelper::log('Beitragslauf', "$title ($count)"); $this->saved(); HeaderUtil::delayedRedirect(LinkHandler::getInstance()->getControllerLink(KasseOverviewPage::class), 2); exit; }
}
"""
php_inv = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\data\user\User;
use wcf\system\exception\UserInputException;
use wcf\page\KasseOverviewPage;
use wcf\system\kasse\KasseHelper;
use wcf\system\user\notification\UserNotificationHandler;
use wcf\data\kasse\KasseInvoiceNotificationObject;
class KasseInvoiceForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function readData(){ parent::readData(); if(!WCF::getSession()->getPermission('user.profile.kasse.canUse')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function save(){ parent::save(); $user=User::getUserByUsername(trim($_POST['usernameSearch'])); if(!$user->userID) throw new UserInputException('usernameSearch','notFound'); $cents=KasseHelper::toCents($_POST['amount']); $db=WCF::getDB(); $db->prepareStatement("INSERT INTO wcf".WCF_N."_wg_invoice (userID,title,amount,status,createdTime,recurrence) VALUES (?,?,?, 'open', ?, ?)")->execute([$user->userID, $_POST['title'], $cents, TIME_NOW, $_POST['recurrence']]); $id=$db->getInsertID('wcf'.WCF_N.'_wg_invoice','invoiceID'); try{ $obj=new KasseInvoiceNotificationObject($id); UserNotificationHandler::getInstance()->fireEvent('invoiceCreated','de.wildesgebilde.kasse.invoice',$obj,[$user->userID]); }catch(\Exception $e){} $this->saved(); HeaderUtil::delayedRedirect(LinkHandler::getInstance()->getControllerLink(KasseOverviewPage::class), 2); exit; }
}
"""
php_claim = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\page\KasseOverviewPage;
use wcf\data\kasse\KasseNotificationObject;
use wcf\system\user\notification\UserNotificationHandler;
use wcf\system\kasse\KasseHelper;
class KasseClaimForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function save(){ parent::save(); $db=WCF::getDB(); $db->prepareStatement("SET NAMES utf8mb4")->execute(); $fn=''; if(isset($_FILES['receiptUpload'])&&!empty($_FILES['receiptUpload']['name'])){ $fn='c_'.TIME_NOW.'_'.WCF::getUser()->userID.'.'.pathinfo($_FILES['receiptUpload']['name'],PATHINFO_EXTENSION); @move_uploaded_file($_FILES['receiptUpload']['tmp_name'],WCF_DIR.'images/kasse/'.$fn); } $cents=KasseHelper::toCents($_POST['amount']); $db->prepareStatement("INSERT INTO wcf".WCF_N."_wg_claim (userID,amount,reason,receipt,status,createdTime,payoutMethod) VALUES (?,?,?,?,'pending',?,?)")->execute([WCF::getUser()->userID,$cents,$_POST['reason'],$fn,TIME_NOW,$_POST['payoutMethod']]); $cid=$db->getInsertID('wcf'.WCF_N.'_wg_claim','claimID'); $admins=KasseHelper::getTreasurers(); if(!empty($admins)) { try{ $obj=new KasseNotificationObject($cid); UserNotificationHandler::getInstance()->fireEvent('claimCreated','de.wildesgebilde.kasse.claim',$obj,$admins); }catch(\Exception $e){} } KasseHelper::log('Rückerstattung beantragt'); $this->saved(); HeaderUtil::delayedRedirect(LinkHandler::getInstance()->getControllerLink(KasseOverviewPage::class), 2); exit; }
}
"""
php_pay_inv = r"""<?php
namespace wcf\action;
use wcf\action\AbstractAction;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\page\KasseOverviewPage;
use wcf\system\kasse\KasseHelper;
use wcf\system\user\notification\UserNotificationHandler;
use wcf\data\kasse\KasseInvoiceNotificationObject;
class KassePayInvoiceAction extends AbstractAction {
    public function execute() {
        parent::execute();
        $id = intval($_REQUEST['id']);
        $userID = WCF::getUser()->userID;
        $isTreasurer = WCF::getSession()->getPermission('user.profile.kasse.canManage');
        $stmt = WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_invoice WHERE invoiceID = ?");
        $stmt->execute([$id]);
        $inv = $stmt->fetchArray();
        if ($inv) {
            $obj = new KasseInvoiceNotificationObject($id);
            if ($inv['status'] == 'open' && $inv['userID'] == $userID) {
                WCF::getDB()->prepareStatement("UPDATE wcf".WCF_N."_wg_invoice SET status = 'pending_approval' WHERE invoiceID = ?")->execute([$id]);
                KasseHelper::log('Zahlung gemeldet', "ID #$id");
                $admins = KasseHelper::getTreasurers();
                if(!empty($admins)) UserNotificationHandler::getInstance()->fireEvent('invoiceReported', 'de.wildesgebilde.kasse.invoice', $obj, $admins);
            } elseif ($inv['status'] == 'pending_approval' && $isTreasurer) {
                WCF::getDB()->prepareStatement("INSERT INTO wcf".WCF_N."_wg_transaction (transactionDate, creationDate, userID, accountType, amount, category, description) VALUES (?, ?, ?, 'bank', ?, 'Zahlung', ?)")->execute([TIME_NOW, TIME_NOW, $inv['userID'], $inv['amount'], 'Beitrag', $inv['title']]);
                WCF::getDB()->prepareStatement("UPDATE wcf".WCF_N."_wg_invoice SET status = 'paid' WHERE invoiceID = ?")->execute([$id]);
                KasseHelper::log('Zahlung bestätigt', "ID #$id");
                UserNotificationHandler::getInstance()->fireEvent('invoiceConfirmed', 'de.wildesgebilde.kasse.invoice', $obj, [$inv['userID']]);
            }
        }
        HeaderUtil::redirect(LinkHandler::getInstance()->getControllerLink(KasseOverviewPage::class));
        exit;
    }
}
"""
php_pay = r"""<?php
namespace wcf\action;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\system\cache\builder\KasseBalanceCacheBuilder;
use wcf\page\KasseAdminClaimsPage;
use wcf\system\kasse\KasseHelper;
class KassePayClaimAction extends AbstractAction {
    public function execute(){
        parent::execute();
        if(!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new \wcf\system\exception\PermissionDeniedException();
        $id=intval($_REQUEST['id']);
        $stmt=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_claim WHERE claimID=?");
        $stmt->execute([$id]);
        $c=$stmt->fetchArray();
        if($c&&$c['status']=='pending'){
            $cat=($c['amount']<0)?'Ausgabe':'Einnahme';
            $acc=$c['payoutMethod']??'bank';
            $sql="INSERT INTO wcf".WCF_N."_wg_transaction (transactionDate,creationDate,userID,accountType,amount,category,description,receipt) VALUES (?,?,?,?,?,?,?,?)";
            WCF::getDB()->prepareStatement($sql)->execute([TIME_NOW,TIME_NOW,$c['userID'],$acc,$c['amount'],$cat,$c['reason'],$c['receipt']]);
            WCF::getDB()->prepareStatement("UPDATE wcf".WCF_N."_wg_claim SET status='paid' WHERE claimID=?")->execute([$id]);
            KasseBalanceCacheBuilder::getInstance()->reset();
            KasseHelper::log('Antrag genehmigt', "ID #$id");
        }
        HeaderUtil::redirect(LinkHandler::getInstance()->getControllerLink(KasseAdminClaimsPage::class));
        exit;
    }
}
"""
php_reject = r"""<?php
namespace wcf\form;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\page\KasseAdminClaimsPage;
use wcf\system\kasse\KasseHelper;
use wcf\system\user\notification\UserNotificationHandler;
use wcf\data\kasse\KasseNotificationObject;
class KasseClaimRejectForm extends AbstractForm {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public $claimID=0;
    public function readParameters(){ parent::readParameters(); if(isset($_REQUEST['id'])) $this->claimID=intval($_REQUEST['id']); }
    public function readData(){ parent::readData(); if(!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function assignVariables(){ parent::assignVariables(); WCF::getTPL()->assign(['claimID'=>$this->claimID]); }
    public function save(){ parent::save(); $reason=$_POST['reason']; WCF::getDB()->prepareStatement("UPDATE wcf".WCF_N."_wg_claim SET status='rejected', rejectReason=? WHERE claimID=?")->execute([$reason, $this->claimID]); KasseHelper::log('Antrag abgelehnt', "ID #{$this->claimID}, Grund: $reason"); try{ $obj=new KasseNotificationObject($this->claimID); UserNotificationHandler::getInstance()->fireEvent('claimRejected','de.wildesgebilde.kasse.claim',$obj,[$obj->getAuthorID()]); }catch(\Exception $e){} HeaderUtil::redirect(LinkHandler::getInstance()->getControllerLink(KasseAdminClaimsPage::class)); exit; }
}
"""
php_mem = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
use wcf\data\user\UserProfile;
use wcf\system\kasse\KasseHelper;
class KasseMembershipPage extends AbstractPage {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function readData() { parent::readData(); if (!WCF::getSession()->getPermission('user.profile.kasse.canUse')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function assignVariables() { parent::assignVariables(); $sql="SELECT u.userID,u.username,f.fee FROM wcf".WCF_N."_user u LEFT JOIN wcf".WCF_N."_wg_user_fee f ON (u.userID=f.userID) ORDER BY u.username"; $stmt=WCF::getDB()->prepareStatement($sql); $stmt->execute(); $users=$stmt->fetchAll(); $uids=array_column($users,'userID'); $profiles=!empty($uids)?UserProfile::getUserProfiles($uids):[]; $members=[]; foreach($users as $u){ $u['userProfile']=$profiles[$u['userID']]??null; $u['fee']=KasseHelper::toFloat($u['fee']??0); $members[]=$u; } WCF::getTPL()->assign(['members'=>$members,'isTreasurer'=>WCF::getSession()->getPermission('user.profile.kasse.canManage')]); }
}
"""
php_cron = r"""<?php
namespace wcf\system\cronjob;
use wcf\data\cronjob\Cronjob;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
class KasseRecurringCronjob extends AbstractCronjob {
    public function execute(Cronjob $cronjob) {
        parent::execute($cronjob);
        $sql="SELECT * FROM wcf".WCF_N."_wg_invoice WHERE recurrence!='none' AND nextDueDate>0 AND nextDueDate<=?";
        $stmt=WCF::getDB()->prepareStatement($sql);
        $stmt->execute([TIME_NOW]);
        while($row=$stmt->fetchArray()){
            if($row['amount']<=0)continue;
            WCF::getDB()->prepareStatement("INSERT INTO wcf".WCF_N."_wg_invoice (userID,title,amount,status,createdTime,recurrence,nextDueDate) VALUES (?,?,?, 'open', ?, 'none', 0)")->execute([$row['userID'], $row['title'].' (Auto)', $row['amount'], TIME_NOW]);
            $next=0;
            if($row['recurrence']=='monthly') $next=strtotime('+1 month',$row['nextDueDate']);
            if($row['recurrence']=='yearly') $next=strtotime('+1 year',$row['nextDueDate']);
            WCF::getDB()->prepareStatement("UPDATE wcf".WCF_N."_wg_invoice SET nextDueDate=? WHERE invoiceID=?")->execute([$next, $row['invoiceID']]);
        }
    }
}
"""
php_cache = r"""<?php
namespace wcf\system\cache\builder;
use wcf\system\WCF;
class KasseBalanceCacheBuilder extends AbstractCacheBuilder {
    protected function rebuild(array $parameters) { return []; }
}
"""
php_history = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
class KasseMyHistoryPage extends AbstractPage {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function assignVariables(){ parent::assignVariables(); $uid=WCF::getUser()->userID; $trans=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_transaction WHERE userID=? ORDER BY transactionDate DESC LIMIT 50"); $trans->execute([$uid]); $rawT=$trans->fetchAll(); $finalT=[]; foreach($rawT as $t){ $t['amount']=KasseHelper::toFloat($t['amount']); $finalT[]=$t; } WCF::getTPL()->assign(['myTransactions'=>$finalT,'myClaims'=>[]]); }
}
"""
php_admin = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
use wcf\data\user\UserProfile;
use wcf\system\kasse\KasseHelper;
class KasseAdminClaimsPage extends AbstractPage {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function assignVariables(){ parent::assignVariables(); if(!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new \wcf\system\exception\PermissionDeniedException(); $stmt=WCF::getDB()->prepareStatement("SELECT * FROM wcf".WCF_N."_wg_claim WHERE status='pending'"); $stmt->execute(); $raw=$stmt->fetchAll(); $uids=array_column($raw,'userID'); $profiles=!empty($uids)?UserProfile::getUserProfiles($uids):[]; $claims=[]; foreach($raw as $c){ $c['userProfile']=$profiles[$c['userID']]??null; $c['amount']=KasseHelper::toFloat($c['amount']); $claims[]=$c; } WCF::getTPL()->assign(['openClaims'=>$claims]); }
}
"""
php_audit = r"""<?php
namespace wcf\page;
use wcf\system\WCF;
class KasseAuditPage extends AbstractPage {
    public $activeMenuItem='de.wildesgebilde.kasse.Overview';
    public function readData(){ parent::readData(); if(!WCF::getSession()->getPermission('user.profile.kasse.canManage')) throw new \wcf\system\exception\PermissionDeniedException(); }
    public function assignVariables(){ parent::assignVariables(); $sql="SELECT * FROM wcf".WCF_N."_wg_audit_log ORDER BY time DESC LIMIT 100"; $stmt=WCF::getDB()->prepareStatement($sql); $stmt->execute(); WCF::getTPL()->assign(['logEntries'=>$stmt->fetchAll()]); }
}
"""
php_export = r"""<?php
namespace wcf\action;
use wcf\action\AbstractAction;
class KasseExportAction extends AbstractAction { public function execute() {} }
"""
php_acp_cat_list = r"""<?php
namespace wcf\acp\page;
use wcf\page\AbstractPage;
use wcf\system\WCF;
class KasseCategoryListPage extends AbstractPage {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.categories';
    public function assignVariables() { parent::assignVariables(); $sql = "SELECT * FROM wcf".WCF_N."_wg_category ORDER BY showOrder"; $stmt = WCF::getDB()->prepareStatement($sql); $stmt->execute(); WCF::getTPL()->assign(['categories' => $stmt->fetchAll()]); }
}
"""
php_acp_cat_add = r"""<?php
namespace wcf\acp\form;
use wcf\form\AbstractForm;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\acp\page\KasseCategoryListPage;
class KasseCategoryAddForm extends AbstractForm {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.categories';
    public function save() { parent::save(); $sql = "INSERT INTO wcf".WCF_N."_wg_category (title, color, icon, showOrder) VALUES (?, ?, ?, ?)"; WCF::getDB()->prepareStatement($sql)->execute([$_POST['title'], $_POST['color'], $_POST['icon'], intval($_POST['showOrder'])]); $this->saved(); HeaderUtil::redirect(LinkHandler::getInstance()->getControllerLink(KasseCategoryListPage::class)); exit; }
}
"""
php_acp_acc_list = r"""<?php
namespace wcf\acp\page;
use wcf\page\AbstractPage;
use wcf\system\WCF;
class KasseAccountListPage extends AbstractPage {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.accounts';
    public function assignVariables() { parent::assignVariables(); $sql = "SELECT * FROM wcf".WCF_N."_wg_account ORDER BY title"; $stmt = WCF::getDB()->prepareStatement($sql); $stmt->execute(); WCF::getTPL()->assign(['accounts' => $stmt->fetchAll()]); }
}
"""
php_acp_acc_add = r"""<?php
namespace wcf\acp\form;
use wcf\form\AbstractForm;
use wcf\system\WCF;
use wcf\util\HeaderUtil;
use wcf\system\request\LinkHandler;
use wcf\acp\page\KasseAccountListPage;
class KasseAccountAddForm extends AbstractForm {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.accounts';
    public function save() { parent::save(); $sql = "INSERT INTO wcf".WCF_N."_wg_account (title, description) VALUES (?, ?)"; WCF::getDB()->prepareStatement($sql)->execute([$_POST['title'], $_POST['description']]); $this->saved(); HeaderUtil::redirect(LinkHandler::getInstance()->getControllerLink(KasseAccountListPage::class)); exit; }
}
"""
php_acp_mem_list = r"""<?php
namespace wcf\acp\page;
use wcf\page\AbstractPage;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
class KasseUserFeeListPage extends AbstractPage {
    public $activeMenuItem = 'wcf.acp.menu.link.kasse.fees';
    public function assignVariables() { parent::assignVariables(); $sql = "SELECT u.userID, u.username, f.fee FROM wcf".WCF_N."_user u LEFT JOIN wcf".WCF_N."_wg_user_fee f ON (u.userID = f.userID) ORDER BY u.username"; $stmt = WCF::getDB()->prepareStatement($sql); $stmt->execute(); $users = $stmt->fetchAll(); $list = []; foreach($users as $u) { $u['fee'] = KasseHelper::toFloat($u['fee'] ?? 0); $list[] = $u; } WCF::getTPL()->assign(['users' => $list]); }
}
"""
php_worker = r"""<?php
namespace wcf\system\worker;
use wcf\system\WCF;
use wcf\system\kasse\KasseHelper;
use wcf\system\cache\builder\KasseBalanceCacheBuilder;
class KasseRebuildDataWorker extends AbstractRebuildDataWorker {
    protected $limit = 500;
    public function execute() { parent::execute(); KasseBalanceCacheBuilder::getInstance()->reset(); }
    public function countObjects() { return 1; }
    protected function initObjectList() {}
    public function getLabel() { return 'Gruppenkasse Daten'; }
}
"""
php_acp_debug = r"""<?php
namespace wcf\acp\page;
use wcf\page\AbstractPage;
class KasseDebugPage extends AbstractPage {}
"""

php_notify_obj = r"""<?php
namespace wcf\data\kasse;
use wcf\system\user\notification\object\IUserNotificationObject;
use wcf\system\request\LinkHandler;
use wcf\page\KasseAdminClaimsPage;
use wcf\system\WCF;
class KasseNotificationObject implements IUserNotificationObject {
    protected $claimID;
    protected $authorID;
    public $reason;
    public function __construct($claimID){ $this->claimID=$claimID; $stmt=WCF::getDB()->prepareStatement("SELECT userID, rejectReason FROM wcf".WCF_N."_wg_claim WHERE claimID=?"); $stmt->execute([$claimID]); $row=$stmt->fetchArray(); if($row){ $this->authorID=$row['userID']; $this->reason=$row['rejectReason']; } }
    public function getObjectID():int{return $this->claimID;}
    public function getTitle():string{return 'Antrag';}
    public function getURL():string{ return \wcf\system\WCF::getSession()->getPermission('user.profile.kasse.canManage') ? LinkHandler::getInstance()->getControllerLink(KasseAdminClaimsPage::class) : LinkHandler::getInstance()->getControllerLink(\wcf\page\KasseOverviewPage::class); }
    public function getAuthorID():int{return (int)$this->authorID;}
    public function __get($name){return null;}
    public function __isset($name){return false;}
    public static function getDatabaseTableName():string{return 'wcf'.WCF_N.'_wg_claim';}
}
"""
php_notify_inv_obj = r"""<?php
namespace wcf\data\kasse;
use wcf\system\user\notification\object\IUserNotificationObject;
use wcf\system\request\LinkHandler;
use wcf\page\KasseOverviewPage;
use wcf\system\WCF;
class KasseInvoiceNotificationObject implements IUserNotificationObject {
    protected $invoiceID;
    protected $userID;
    protected $title;
    public function __construct($invoiceID){ $this->invoiceID=$invoiceID; $stmt=WCF::getDB()->prepareStatement("SELECT userID,title FROM wcf".WCF_N."_wg_invoice WHERE invoiceID=?"); $stmt->execute([$invoiceID]); $row=$stmt->fetchArray(); if($row){ $this->userID=$row['userID']; $this->title=$row['title']; } }
    public function getObjectID():int{return $this->invoiceID;}
    public function getTitle():string{return $this->title??'Forderung';}
    public function getURL():string{return LinkHandler::getInstance()->getControllerLink(KasseOverviewPage::class);}
    public function getAuthorID():int{return 0;}
    public function __get($name){return null;}
    public function __isset($name){return false;}
    public static function getDatabaseTableName():string{return 'wcf'.WCF_N.'_wg_invoice';}
}
"""

php_notify_evt = r"""<?php
namespace wcf\system\user\notification\event;
use wcf\system\user\notification\event\AbstractUserNotificationEvent;
class KasseClaimCreatedUserNotificationEvent extends AbstractUserNotificationEvent {
    public function getTitle():string{return 'Neuer Antrag';}
    public function getMessage():string{return 'Ein neuer Antrag wurde erstellt.';}
    public function getEmailMessage($t='instant'){return $this->getMessage();}
    public function getLink():string{return $this->getUserNotificationObject()->getURL();}
}
"""
php_notify_inv_evt = r"""<?php
namespace wcf\system\user\notification\event;
use wcf\system\user\notification\event\AbstractUserNotificationEvent;
class KasseInvoiceCreatedUserNotificationEvent extends AbstractUserNotificationEvent {
    public function getTitle():string{return 'Neue Zahlungsaufforderung';}
    public function getMessage():string{return 'Du hast eine neue Forderung erhalten: '.$this->getUserNotificationObject()->getTitle();}
    public function getEmailMessage($t='instant'){return $this->getMessage();}
    public function getLink():string{return $this->getUserNotificationObject()->getURL();}
}
"""
php_notify_rej = r"""<?php
namespace wcf\system\user\notification\event;
use wcf\system\user\notification\event\AbstractUserNotificationEvent;
class KasseClaimRejectedUserNotificationEvent extends AbstractUserNotificationEvent {
    public function getTitle(): string { return 'Antrag abgelehnt'; }
    public function getMessage(): string { return 'Dein Antrag wurde abgelehnt. Grund: ' . $this->getUserNotificationObject()->reason; }
    public function getEmailMessage($t='instant'){return $this->getMessage();}
    public function getLink():string{return $this->getUserNotificationObject()->getURL();}
}
"""
php_notify_rep = r"""<?php
namespace wcf\system\user\notification\event;
use wcf\system\user\notification\event\AbstractUserNotificationEvent;
class KasseInvoiceReportedUserNotificationEvent extends AbstractUserNotificationEvent {
    public function getTitle(): string { return 'Zahlung gemeldet'; }
    public function getMessage(): string { return 'Ein Mitglied hat eine Zahlung gemeldet.'; }
    public function getEmailMessage($t='instant'){return $this->getMessage();}
    public function getLink():string{return $this->getUserNotificationObject()->getURL();}
}
"""
php_notify_con = r"""<?php
namespace wcf\system\user\notification\event;
use wcf\system\user\notification\event\AbstractUserNotificationEvent;
class KasseInvoiceConfirmedUserNotificationEvent extends AbstractUserNotificationEvent {
    public function getTitle(): string { return 'Zahlung bestätigt'; }
    public function getMessage(): string { return 'Deine Zahlung für "' . $this->getUserNotificationObject()->getTitle() . '" wurde bestätigt.'; }
    public function getEmailMessage($t='instant'){return $this->getMessage();}
    public function getLink():string{return $this->getUserNotificationObject()->getURL();}
}
"""

# ==========================================================================
# 3. TEMPLATES
# ==========================================================================

tpl_acp_status = r"""{if $kasseChecks|isset}<div class=\"sectionBox\"><h2 class=\"sectionTitle\">System-Status</h2><div class=\"tabularBox\"><table class=\"table\"><thead><tr><th>Prüfung</th><th>Status</th></tr></thead><tbody><tr><td>Datenbank</td><td>{if $kasseChecks.db}<span class=\"badge green\">OK</span>{else}<span class=\"badge red\">Fehler</span>{/if}</td></tr><tr><td>Ordner</td><td>{if $kasseChecks.dir}<span class=\"badge green\">OK</span>{else}<span class=\"badge red\">NO</span>{/if}</td></tr></tbody></table></div></div>{/if}"""

tpl_overview = r"""{include file='header'}
<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Gruppenkasse</h1></div></header>
<div class="kasse-grid">
    <div class="kasse-card highlight">
        <div class="label">Gesamtbestand</div>
        <div class="amount">{$balances.total|default:0|currency}</div>
        <div class="kasse-sub-stats">
            <div><span class="icon icon24 fa-brands fa-paypal"></span> {$balances.paypal|default:0|currency}</div>
            <div><span class="icon icon24 fa-solid fa-building-columns"></span> {$balances.bank|default:0|currency}</div>
            <div><span class="icon icon24 fa-solid fa-wallet"></span> {$balances.cash|default:0|currency}</div>
        </div>
    </div>
    <div class="kasse-card">
        <div class="label">Mein Bereich</div>
        <div class="amount"><span class="icon icon48 fa-solid fa-user-lock"></span></div>
        <a href="{link controller='KasseClaim'}{/link}" class="button buttonPrimary full-width">Rückerstattung anfordern</a>
        <a href="{link controller='KasseInvoice'}{/link}" class="button full-width" style="margin-top:5px;">Forderung stellen</a>
    </div>
    {if $isTreasurer}
    <div class="kasse-card">
        <div class="label">Kassenwart</div>
        <div class="amount"><span class="icon icon48 fa-solid fa-shield-halved"></span></div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:5px;">
            <a href="{link controller='KasseFee'}{/link}" class="button buttonPrimary small">Beitragslauf</a>
            <a href="{link controller='KasseAdd'}{/link}" class="button small">Buchen</a>
            <a href="{link controller='KasseAdminClaims'}{/link}" class="button small">Prüfung</a>
            <a href="{link controller='KasseAudit'}{/link}" class="button small">Protokoll</a>
            <a href="{link controller='KasseImport'}{/link}" class="button small">CSV Import</a>
        </div>
    </div>
    {/if}
</div>

{if $projects|count > 0}
<div class="sectionBox">
    <h2 class="sectionTitle">Laufende Projekte</h2>
    <div class="kasse-project-list">
        {foreach from=$projects item=p}
        <div class="kasse-project">
            <h3>{$p.title} <span>{$p.currentSum|currency} / {$p.targetAmount|currency}</span></h3>
            <div class="project-meta">{$p.description}</div>
            <div class="progress-bar-wrap"><div class="progress-bar" style="width: {$p.percent}%;"></div><div class="progress-text">{$p.percent}%</div></div>
        </div>
        {/foreach}
    </div>
</div>
{/if}

{if $myInvoices|count > 0}
<div class="warning">
    <h3>Offene Forderungen</h3>
    <table class="table"><thead><tr><th>Titel</th><th>Betrag</th><th>Status</th><th>Aktion</th></tr></thead><tbody>
    {foreach from=$myInvoices item=inv}
        <tr>
            <td>{$inv.title}</td>
            <td>{$inv.amount|currency}</td>
            <td>{if $inv.status == 'open'}<span class="badge red">Offen</span>{elseif $inv.status == 'pending_approval'}<span class="badge orange">Prüfung...</span>{/if}</td>
            <td>{if $inv.status == 'open'}<a href="{link controller='KassePayInvoice' id=$inv.invoiceID}{/link}" class="button small buttonPrimary">Zahlung melden</a> <a href="{link controller='KasseInvoicePrint' id=$inv.invoiceID}{/link}" target="_blank" class="button small">Drucken</a>{else}<button disabled class="button small disabled">Gemeldet</button>{/if}</td>
        </tr>
    {/foreach}
    </tbody></table>
</div>
{/if}
{if $isTreasurer && $adminPendingInvoices|count > 0}
<div class="info">
    <h3>Zahlungseingänge bestätigen</h3>
    <table class="table"><thead><tr><th>User</th><th>Titel</th><th>Betrag</th><th>Aktion</th></tr></thead><tbody>
    {foreach from=$adminPendingInvoices item=inv}
        <tr><td>{$inv.username}</td><td>{$inv.title}</td><td>{$inv.amount|currency}</td><td><a href="{link controller='KassePayInvoice' id=$inv.invoiceID}{/link}" class="button small buttonPrimary">Bestätigen</a></td></tr>
    {/foreach}
    </tbody></table>
</div>
{/if}
<div class="kasse-nav" style="margin-top:30px; text-align:center;">
    <a href="{link controller='KasseLog'}{/link}" class="button"><span class="icon icon16 fa-solid fa-list"></span> <span>Journal</span></a>
    <a href="{link controller='KasseMembership'}{/link}" class="button"><span class="icon icon16 fa-solid fa-users"></span> <span>Mitglieder</span></a>
</div>
{include file='footer'}"""

tpl_log = r"""{include file='header'}
<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Journal</h1></div>
<nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseOverview'}{/link}" class="button"><span class="icon icon16 fa-solid fa-arrow-left"></span> <span>Zurück</span></a></li></ul></nav></header>
<div class="section">
    <form method="get" action="{link controller='KasseLog'}{/link}">
        <select name="category" onchange="this.form.submit()">
            <option value="">Alle Kategorien</option>
            {foreach from=$availableCategories item=cat}
                <option value="{$cat.title}" {if $filterCategory == $cat.title}selected{/if}>{$cat.title}</option>
            {/foreach}
        </select>
    </form>
</div>
<div class="section tabularBox">
    <div class="responsive-table-wrap">
        <table class="table kasse-mobile-cards">
            <thead><tr><th>Datum</th><th>User</th><th>Kategorie</th><th>Betrag</th><th>Beschreibung</th></tr></thead>
            <tbody>
            {foreach from=$entries item=e}
                <tr>
                    <td data-label="Datum">{$e.transactionDate|date}</td>
                    <td data-label="User">{$e.username}</td>
                    <td data-label="Kategorie">{$e.category}</td>
                    <td data-label="Betrag" style="color:{if $e.amount<0}red{else}green{/if}">{$e.amount|currency}</td>
                    <td data-label="Info">{$e.description}</td>
                </tr>
            {/foreach}
            </tbody>
        </table>
    </div>
</div>
{include file='footer'}"""

tpl_add = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Buchung</h1></div></header><form method="post" action="{link controller='KasseAdd'}{/link}"><div class="section kasse-form"><dl><dt>Betrag</dt><dd><input type="text" name="amount" class="long"></dd></dl><dl><dt>Kategorie</dt><dd><select name="category">{foreach from=$categories item=c}<option value="{$c.title}">{$c.title}</option>{/foreach}</select></dd></dl><dl><dt>Projekt (Optional)</dt><dd><select name="projectID"><option value="0">Kein Projekt</option>{foreach from=$projects item=p}<option value="{$p.projectID}">{$p.title}</option>{/foreach}</select></dd></dl><dl><dt>Konto</dt><dd><select name="accountType"><option value="bank">Bank</option><option value="paypal">PayPal</option><option value="cash">Bar</option></select></dd></dl><dl><dt>Beschreibung</dt><dd><textarea name="description"></textarea></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Speichern</button></div></form>{include file='footer'}"""
tpl_acp_proj_list = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Projekte</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseProjectAdd'}{/link}" class="button"><span class="icon icon16 fa-solid fa-plus"></span> <span>Projekt hinzufügen</span></a></li></ul></nav></header><div class="section tabularBox"><table class="table"><thead><tr><th>Titel</th><th>Ziel</th><th>Status</th></tr></thead><tbody>{foreach from=$projects item=p}<tr><td>{$p.title}</td><td>{$p.targetAmount|currency}</td><td>{$p.status}</td></tr>{/foreach}</tbody></table></div>{include file='footer'}"""
tpl_acp_proj_add = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Projekt erstellen</h1></div></header><form method="post" action="{link controller='KasseProjectAdd'}{/link}"><div class="section"><dl><dt>Titel</dt><dd><input type="text" name="title" class="long" required></dd></dl><dl><dt>Beschreibung</dt><dd><textarea name="description" class="long"></textarea></dd></dl><dl><dt>Zielbetrag</dt><dd><input type="text" name="targetAmount" class="long" required></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Speichern</button></div></form>{include file='footer'}"""
tpl_claim = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Rückerstattung</h1></div></header><form method="post" action="{link controller='KasseClaim'}{/link}" enctype="multipart/form-data"><div class="section kasse-form"><dl><dt>Betrag</dt><dd><input type="text" name="amount" class="long" required></dd></dl><dl><dt>Grund</dt><dd><textarea name="reason" class="long"></textarea></dd></dl><dl><dt>Beleg</dt><dd><input type="file" name="receiptUpload"></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Absenden</button></div></form>{include file='footer'}"""
tpl_inv = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Forderung erstellen</h1></div></header><div class="info">Erstelle eine Zahlungsaufforderung an ein Mitglied.</div><form method="post" action="{link controller='KasseInvoice'}{/link}"><div class="section kasse-form"><dl><dt>Benutzername</dt><dd><input type="text" name="usernameSearch" class="long" required value="{$prefillUsername|default:''}"></dd></dl><dl><dt>Titel / Grund</dt><dd><input type="text" name="title" class="long" required></dd></dl><dl><dt>Betrag</dt><dd><input type="text" name="amount" class="long" required></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Forderung senden</button></div></form>{include file='footer'}"""
tpl_fee = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Beitragslauf</h1></div></header><div class="info">Zieht den hinterlegten Beitrag bei ALLEN Nutzern ein.</div><form method="post" action="{link controller='KasseFee'}{/link}"><div class="section kasse-form"><dl><dt>Titel</dt><dd><input type="text" name="title" class="long" required value="Monatsbeitrag"></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Starten</button></div></form>{include file='footer'}"""
tpl_hist = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Verlauf</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseOverview'}{/link}" class="button"><span class="icon icon16 fa-solid fa-arrow-left"></span> <span>Zurück</span></a></li></ul></nav></header><div class="section tabularBox"><div class="responsive-table-wrap"><table class="table"><thead><tr><th>Datum</th><th>Kategorie</th><th>Betrag</th></tr></thead><tbody>{foreach from=$myTransactions item=t}<tr><td>{$t.transactionDate|date}</td><td>{$t.category}</td><td style="color:{if $t.amount<0}red{else}green{/if}">{$t.amount|currency}</td></tr>{/foreach}</tbody></table></div></div>{include file='footer'}"""
tpl_admin = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Ausgaben Prüfung</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseOverview'}{/link}" class="button"><span class="icon icon16 fa-solid fa-arrow-left"></span> <span>Zurück</span></a></li></ul></nav></header><div class="section tabularBox">{if $openClaims|count > 0}<table class="table"><thead><tr><th>User</th><th>Grund</th><th>Betrag</th><th>Aktion</th></tr></thead><tbody>{foreach from=$openClaims item=c}<tr><td>{$c.userProfile->username}</td><td>{$c.reason}</td><td>{$c.amount|currency}</td><td><a href="{link controller='KassePayClaim' id=$c.claimID}{/link}" class="button small">Zahlen</a> <a href="{link controller='KasseClaimReject' id=$c.claimID}{/link}" class="button small">Ablehnen</a></td></tr>{/foreach}</tbody></table>{else}<p>Leer</p>{/if}</div>{include file='footer'}"""
tpl_mem = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Mitglieder</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseOverview'}{/link}" class="button"><span class="icon icon16 fa-solid fa-arrow-left"></span> <span>Zurück</span></a></li></ul></nav></header><div class="section tabularBox"><table class="table"><thead><tr><th colspan="2">Mitglied</th><th>Beitrag</th>{if $isTreasurer}<th></th>{/if}</tr></thead><tbody>{foreach from=$members item=m}<tr><td class="columnIcon">{@$m.userProfile->getAvatar()->getImageTag(32)}</td><td>{$m.username}</td><td>{$m.fee|currency}</td>{if $isTreasurer}<td><a href="{link controller='KasseUserFee' id=$m.userID}{/link}" class="button small" title="Beitrag bearbeiten"><span class="icon icon16 fa-solid fa-pen"></span></a> <a href="{link controller='KasseInvoice' username=$m.username}{/link}" class="button small" title="Forderung"><span class="icon icon16 fa-solid fa-file-invoice-dollar"></span></a></td>{/if}</tr>{/foreach}</tbody></table></div>{include file='footer'}"""
tpl_user_fee = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Beitrag bearbeiten: {$editUser->username}</h1></div></header><form method="post" action="{link controller='KasseUserFee' id=$editUser->userID}{/link}"><div class="section kasse-form"><dl><dt>Aktueller Beitrag</dt><dd><input type="text" name="amount" class="long" value="{$currentFee|number_format:2:',':'.'}"></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Speichern</button></div></form>{include file='footer'}"""
tpl_audit = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Protokoll</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseOverview'}{/link}" class="button"><span class="icon icon16 fa-solid fa-arrow-left"></span> <span>Zurück</span></a></li></ul></nav></header><div class="section tabularBox"><div class="responsive-table-wrap"><table class="table"><thead><tr><th>Zeit</th><th>User</th><th>Aktion</th><th>Details</th></tr></thead><tbody>{foreach from=$logEntries item=l}<tr><td>{$l.time|time}</td><td>{$l.username}</td><td>{$l.action}</td><td>{$l.details}</td></tr>{/foreach}</tbody></table></div></div>{include file='footer'}"""
tpl_reject = r"""{include file='header'}""" + css_global + r"""<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Antrag ablehnen</h1></div></header><form method="post" action="{link controller='KasseClaimReject' id=$claimID}{/link}"><div class="section kasse-form"><dl><dt>Begründung</dt><dd><textarea name="reason" class="long" required></textarea></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Ablehnen</button></div></form>{include file='footer'}"""
tpl_print = r"""<!DOCTYPE html><html><head><title>Rechnung #{$invoice.invoiceID}</title><style>body{font-family:sans-serif;padding:40px;}.box{border:1px solid #ccc;padding:20px;}h1{border-bottom:1px solid #000;}</style></head><body onload="window.print()"><div class="box"><h1>Rechnung #{$invoice.invoiceID}</h1><p>Datum: {$printDate|date}</p><p>Titel: {$invoice.title}</p><h2>Betrag: {$invoice.amount|currency}</h2><p>Status: {$invoice.status}</p></div></body></html>"""
tpl_import = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">CSV Import (Beta)</h1></div></header>{if $success}<p class="success">Import erfolgreich!</p>{/if}<form method="post" action="{link controller='KasseImport'}{/link}" enctype="multipart/form-data"><div class="section"><dl><dt>CSV Datei</dt><dd><input type="file" name="csvFile" required></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Importieren</button></div></form>{include file='footer'}"""
tpl_acp_cat_list = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Kategorien</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseCategoryAdd'}{/link}" class="button"><span class="icon icon16 fa-solid fa-plus"></span> <span>Kategorie hinzufügen</span></a></li></ul></nav></header><div class="section tabularBox"><table class="table"><thead><tr><th>ID</th><th>Titel</th><th>Farbe</th><th>Icon</th></tr></thead><tbody>{foreach from=$categories item=c}<tr><td>{$c.categoryID}</td><td>{$c.title}</td><td><span class="badge" style="background-color:{$c.color}">{$c.color}</span></td><td><span class="icon fa-solid fa-{$c.icon}"></span></td></tr>{/foreach}</tbody></table></div>{include file='footer'}"""
tpl_acp_cat_add = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Kategorie erstellen</h1></div></header><form method="post" action="{link controller='KasseCategoryAdd'}{/link}"><div class="section"><dl><dt>Titel</dt><dd><input type="text" name="title" class="long" required></dd></dl><dl><dt>Farbe (Hex)</dt><dd><input type="text" name="color" class="long" placeholder="#ff0000"></dd></dl><dl><dt>Icon (FontAwesome Name ohne fa-)</dt><dd><input type="text" name="icon" class="long" placeholder="star"></dd></dl><dl><dt>Reihenfolge</dt><dd><input type="number" name="showOrder" value="0"></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Speichern</button></div></form>{include file='footer'}"""
tpl_acp_acc_list = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Konten</h1></div><nav class="contentHeaderNavigation"><ul><li><a href="{link controller='KasseAccountAdd'}{/link}" class="button"><span class="icon icon16 fa-solid fa-plus"></span> <span>Konto hinzufügen</span></a></li></ul></nav></header><div class="section tabularBox"><table class="table"><thead><tr><th>ID</th><th>Titel</th><th>Beschreibung</th></tr></thead><tbody>{foreach from=$accounts item=a}<tr><td>{$a.accountID}</td><td>{$a.title}</td><td>{$a.description}</td></tr>{/foreach}</tbody></table></div>{include file='footer'}"""
tpl_acp_acc_add = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Konto erstellen</h1></div></header><form method="post" action="{link controller='KasseAccountAdd'}{/link}"><div class="section"><dl><dt>Titel</dt><dd><input type="text" name="title" class="long" required></dd></dl><dl><dt>Beschreibung</dt><dd><textarea name="description" class="long"></textarea></dd></dl></div><div class="formSubmit"><button class="buttonPrimary">Speichern</button></div></form>{include file='footer'}"""
tpl_acp_mem_list = r"""{include file='header'}<header class="contentHeader"><div class="contentHeaderTitle"><h1 class="contentTitle">Mitglieder Beiträge</h1></div></header><div class="section tabularBox"><table class="table"><thead><tr><th>User</th><th>Aktueller Beitragssatz</th></tr></thead><tbody>{foreach from=$users item=u}<tr><td>{$u.username}</td><td>{$u.fee|currency}</td></tr>{/foreach}</tbody></table></div>{include file='footer'}"""

# ==========================================================================
# 3. XML CONFIG
# ==========================================================================

package_xml = r"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.woltlab.com" name="de.wildesgebilde.kasse">
    <packageinformation>
        <packagename><![CDATA[Gruppenkasse]]></packagename>
        <packagedescription><![CDATA[Einfaches Kassen- und Beitrags-Plugin.]]></packagedescription>
        <version>2.0.5</version>
        <requiredversion>6.1</requiredversion>
    </packageinformation>
    <authorinformation>
        <author><![CDATA[Wildes Gebilde]]></author>
    </authorinformation>
    <install>
        <instruction type="acpMenu">acpMenu.xml</instruction>
        <instruction type="language">language/de.xml</instruction>
        <instruction type="page">page.xml</instruction>
        <instruction type="menuItem">menuItem.xml</instruction>
        <instruction type="option">option.xml</instruction>
        <instruction type="userGroupOption">userGroupOption.xml</instruction>
        <instruction type="userNotificationEvent">userNotificationEvent.xml</instruction>
        <instruction type="eventListener">eventListener.xml</instruction>
        <instruction type="templateListener">templateListener.xml</instruction>
        <instruction type="objectType">objectType.xml</instruction>
        <instruction type="sql">install.sql</instruction>
    </install>
</package>
"""

ug_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/userGroupOption.xsd\">
    <import>
        <option type=\"boolean\">
            <name>user.profile.kasse.canUse</name>
            <categoryname>wcf.user.profile</categoryname>
        </option>
        <option type=\"boolean\">
            <name>user.profile.kasse.canManage</name>
            <categoryname>wcf.user.profile</categoryname>
        </option>
    </import>
</data>
"""

page_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/page.xsd\">
    <import>
        <page name=\"KasseOverview\" controller=\"wcf\\page\\KasseOverviewPage\"/>
        <page name=\"KasseLog\" controller=\"wcf\\page\\KasseLogPage\"/>
        <page name=\"KasseClaim\" controller=\"wcf\\form\\KasseClaimForm\"/>
        <page name=\"KasseAdd\" controller=\"wcf\\form\\KasseAddForm\"/>
        <page name=\"KasseInvoice\" controller=\"wcf\\form\\KasseInvoiceForm\"/>
        <page name=\"KasseFee\" controller=\"wcf\\form\\KasseFeeForm\"/>
        <page name=\"KasseUserFee\" controller=\"wcf\\form\\KasseUserFeeForm\"/>
        <page name=\"KasseAudit\" controller=\"wcf\\page\\KasseAuditPage\"/>
        <page name=\"KasseMyHistory\" controller=\"wcf\\page\\KasseMyHistoryPage\"/>
        <page name=\"KasseAdminClaims\" controller=\"wcf\\page\\KasseAdminClaimsPage\"/>
        <page name=\"KasseMembership\" controller=\"wcf\\page\\KasseMembershipPage\"/>
        <page name=\"KasseClaimReject\" controller=\"wcf\\form\\KasseClaimRejectForm\"/>
        <page name=\"KasseImport\" controller=\"wcf\\form\\KasseImportForm\"/>
        <page name=\"KasseInvoicePrint\" controller=\"wcf\\page\\KasseInvoicePrintPage\"/>
        <page name=\"KassePayInvoice\" controller=\"wcf\\action\\KassePayInvoiceAction\"/>
        <page name=\"KassePayClaim\" controller=\"wcf\\action\\KassePayClaimAction\"/>
        <page name=\"KasseExport\" controller=\"wcf\\action\\KasseExportAction\"/>
    </import>
</data>
"""

menu_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/menuItem.xsd\">
    <import>
        <menuitem name=\"de.wildesgebilde.kasse.Overview\">
            <title>Gruppenkasse</title>
            <controller>KasseOverview</controller>
            <showorder>1</showorder>
        </menuitem>
        <menuitem name=\"de.wildesgebilde.kasse.Log\">
            <title>Journal</title>
            <controller>KasseLog</controller>
            <showorder>2</showorder>
        </menuitem>
    </import>
</data>
"""

option_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/option.xsd\">
    <import>
        <category name=\"kasse.general\" showorder=\"1\"/>
    </import>
</data>
"""

notify_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/userNotificationEvent.xsd\">
    <import>
        <event>
            <name>de.wildesgebilde.kasse.claim</name>
            <definitionname>com.woltlab.wcf.user.notification.event</definitionname>
            <classname>wcf\\system\\user\\notification\\event\\KasseClaimCreatedUserNotificationEvent</classname>
            <objecttype>de.wildesgebilde.kasse.claim.object</objecttype>
        </event>
        <event>
            <name>de.wildesgebilde.kasse.invoice</name>
            <definitionname>com.woltlab.wcf.user.notification.event</definitionname>
            <classname>wcf\\system\\user\\notification\\event\\KasseInvoiceCreatedUserNotificationEvent</classname>
            <objecttype>de.wildesgebilde.kasse.invoice.object</objecttype>
        </event>
    </import>
</data>
"""

evt_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/eventListener.xsd\">
    <import>
        <listener>
            <eventclassname>wcf\\acp\\form\\OptionForm</eventclassname>
            <eventname>assignVariables</eventname>
            <listenerclassname>wcf\\system\\event\\listener\\KasseACPOptionListener</listenerclassname>
        </listener>
    </import>
</data>
"""

tpl_lst_xml = r"""<?xml version="1.0" encoding="UTF-8"?>
<data xmlns="http://www.woltlab.com" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.woltlab.com http://www.woltlab.com/XSD/2019/templateListener.xsd">
    <import>
        <listener>
            <eventname>optionFormCategoryFooter</eventname>
            <templatename>optionForm</templatename>
            <template>kasseACPStatus</template>
        </listener>
    </import>
</data>
"""

acp_menu = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/acpMenu.xsd\">
    <import>
        <acpmenuitem name=\"wcf.acp.menu.link.kasse\">
            <parent>wcf.acp.menu.link.configuration</parent>
            <showorder>99</showorder>
        </acpmenuitem>
        <acpmenuitem name=\"wcf.acp.menu.link.kasse.settings\">
            <parent>wcf.acp.menu.link.kasse</parent>
            <controller>wcf\\acp\\form\\OptionForm</controller>
            <parameter>category=kasse.general</parameter>
        </acpmenuitem>
        <acpmenuitem name=\"wcf.acp.menu.link.kasse.categories\">
            <parent>wcf.acp.menu.link.kasse</parent>
            <controller>wcf\\acp\\page\\KasseCategoryListPage</controller>
        </acpmenuitem>
        <acpmenuitem name=\"wcf.acp.menu.link.kasse.projects\">
            <parent>wcf.acp.menu.link.kasse</parent>
            <controller>wcf\\acp\\page\\KasseProjectListPage</controller>
        </acpmenuitem>
        <acpmenuitem name=\"wcf.acp.menu.link.kasse.accounts\">
            <parent>wcf.acp.menu.link.kasse</parent>
            <controller>wcf\\acp\\page\\KasseAccountListPage</controller>
        </acpmenuitem>
        <acpmenuitem name=\"wcf.acp.menu.link.kasse.fees\">
            <parent>wcf.acp.menu.link.kasse</parent>
            <controller>wcf\\acp\\page\\KasseUserFeeListPage</controller>
        </acpmenuitem>
    </import>
</data>
"""

install_sql = r"""CREATE TABLE IF NOT EXISTS wcf1_wg_transaction (transactionID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, transactionDate INT(10), creationDate INT(10), userID INT(10), projectID INT(10) DEFAULT 0, accountType VARCHAR(20), type VARCHAR(10), amount INT(10), category VARCHAR(255), purpose VARCHAR(255), description TEXT, receipt VARCHAR(255)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_claim (claimID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, userID INT(10), amount INT(10), reason VARCHAR(255), receipt VARCHAR(255), status VARCHAR(20), createdTime INT(10), payoutMethod VARCHAR(20), payoutDetails TEXT, rejectReason TEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_invoice (invoiceID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, userID INT(10), title VARCHAR(255), amount INT(10), status VARCHAR(20) DEFAULT 'open', createdTime INT(10), recurrence VARCHAR(20) DEFAULT 'none', nextDueDate INT(10) DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_user_fee (userID INT(10) NOT NULL PRIMARY KEY, fee INT(10) NOT NULL DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_audit_log (logID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, userID INT(10), username VARCHAR(255), action VARCHAR(255), details TEXT, time INT(10)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_category (categoryID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255), color VARCHAR(7), icon VARCHAR(50), showOrder INT(10) DEFAULT 0, budget INT(10) DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_account (accountID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255), description TEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; CREATE TABLE IF NOT EXISTS wcf1_wg_project (projectID INT(10) NOT NULL AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255), description TEXT, targetAmount INT(10) DEFAULT 0, status VARCHAR(20) DEFAULT 'open') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci; INSERT IGNORE INTO wcf1_user_group_option_value (groupID, optionID, optionValue) SELECT 4, optionID, 1 FROM wcf1_user_group_option WHERE optionName IN ('user.profile.kasse.canUse', 'user.profile.kasse.canManage');"""

object_type_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<data xmlns=\"http://www.woltlab.com\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.woltlab.com http://www.woltlab.com/XSD/2019/objectType.xsd\">
    <import>
        <type>
            <name>de.wildesgebilde.kasse.trophy.contribution</name>
            <definitionname>com.woltlab.wcf.user.trophy.criterion</definitionname>
            <classname>wcf\\system\\user\\trophy\\criterion\\KasseContributionCriterion</classname>
            <categoryname>de.wildesgebilde.kasse</categoryname>
        </type>
        <type>
            <name>de.wildesgebilde.kasse.claim.object</name>
            <definitionname>com.woltlab.wcf.user.notification.object</definitionname>
            <classname>wcf\\data\\kasse\\KasseNotificationObject</classname>
            <categoryname>de.wildesgebilde.kasse</categoryname>
        </type>
        <type>
            <name>de.wildesgebilde.kasse.invoice.object</name>
            <definitionname>com.woltlab.wcf.user.notification.object</definitionname>
            <classname>wcf\\data\\kasse\\KasseInvoiceNotificationObject</classname>
            <categoryname>de.wildesgebilde.kasse</categoryname>
        </type>
    </import>
</data>
"""

lang_xml = r"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<language xmlns=\"http://www.woltlab.com\" languagecode=\"de\">
    <import>
        <category name=\"wcf.acp.menu\">
            <item name=\"wcf.acp.menu.link.kasse\"><![CDATA[Gruppenkasse]]></item>
            <item name=\"wcf.acp.menu.link.kasse.settings\"><![CDATA[Einstellungen]]></item>
            <item name=\"wcf.acp.menu.link.kasse.categories\"><![CDATA[Kategorien]]></item>
            <item name=\"wcf.acp.menu.link.kasse.projects\"><![CDATA[Projekte]]></item>
            <item name=\"wcf.acp.menu.link.kasse.accounts\"><![CDATA[Konten]]></item>
            <item name=\"wcf.acp.menu.link.kasse.fees\"><![CDATA[Mitglieder]]></item>
        </category>
        <category name=\"wcf.user.trophy\">
            <item name=\"wcf.user.trophy.criterion.de.wildesgebilde.kasse.trophy.contribution\"><![CDATA[Eingezahlter Betrag (Kasse)]]></item>
            <item name=\"wcf.user.trophy.criterion.de.wildesgebilde.kasse.trophy.contribution.description\"><![CDATA[Der Benutzer hat insgesamt mindestens so viel Euro in die Kasse eingezahlt.]]></item>
        </category>
    </import>
</language>
"""

# ==========================================================================
# 4. PACKING
# ==========================================================================
try:
    print("Erstelle Paket V205...")

    files_io = io.BytesIO()
    with tarfile.open(fileobj=files_io, mode='w') as tar:
        info = tarfile.TarInfo(name="images/kasse/index.html")
        info.size = 0
        info.mtime = time.time()
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(b""))
        info = tarfile.TarInfo(name="style/ui/kasse.scss")
        info.size = len(scss_content)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(scss_content.encode('utf-8')))

        file_map = [
            ("lib/page/KasseOverviewPage.class.php", php_overview),
            ("lib/page/KasseLogPage.class.php", php_log),
            ("lib/page/KasseInvoicePrintPage.class.php", php_print),
            ("lib/form/KasseClaimRejectForm.class.php", php_reject),
            ("lib/form/KasseImportForm.class.php", php_import),
            ("lib/form/KasseAddForm.class.php", php_add),
            ("lib/system/kasse/KasseHelper.class.php", php_helper),
            ("lib/system/event/listener/KasseACPOptionListener.class.php", php_listener),
            ("lib/system/user/trophy/criterion/KasseContributionCriterion.class.php", php_trophy),
            ("lib/acp/page/KasseProjectListPage.class.php", php_acp_proj_list),
            ("lib/acp/form/KasseProjectAddForm.class.php", php_acp_proj_add),
            ("lib/data/kasse/transaction/KasseTransaction.class.php", php_trans_obj),
            ("lib/data/kasse/transaction/KasseTransactionList.class.php", php_trans_list),
            ("lib/data/kasse/project/KasseProject.class.php", php_proj_obj),
            ("lib/data/kasse/project/KasseProjectList.class.php", php_proj_list),
            ("lib/page/KasseAuditPage.class.php", php_audit),
            ("lib/page/KasseMyHistoryPage.class.php", php_history),
            ("lib/page/KasseAdminClaimsPage.class.php", php_admin),
            ("lib/page/KasseMembershipPage.class.php", php_mem),
            ("lib/form/KasseClaimForm.class.php", php_claim),
            ("lib/form/KasseInvoiceForm.class.php", php_inv),
            ("lib/form/KasseFeeForm.class.php", php_fee_run),
            ("lib/form/KasseUserFeeForm.class.php", php_fee_edit),
            ("lib/system/cronjob/KasseRecurringCronjob.class.php", php_cron),
            ("lib/system/cache/builder/KasseBalanceCacheBuilder.class.php", php_cache),
            ("lib/system/worker/KasseRebuildDataWorker.class.php", php_worker),
            ("lib/data/kasse/KasseNotificationObject.class.php", php_notify_obj),
            ("lib/data/kasse/KasseInvoiceNotificationObject.class.php", php_notify_inv_obj),
            ("lib/system/user/notification/event/KasseClaimCreatedUserNotificationEvent.class.php", php_notify_evt),
            ("lib/system/user/notification/event/KasseClaimRejectedUserNotificationEvent.class.php", php_notify_rej),
            ("lib/system/user/notification/event/KasseInvoiceCreatedUserNotificationEvent.class.php", php_notify_inv_evt),
            ("lib/system/user/notification/event/KasseInvoiceReportedUserNotificationEvent.class.php", php_notify_rep),
            ("lib/system/user/notification/event/KasseInvoiceConfirmedUserNotificationEvent.class.php", php_notify_con),
            ("lib/action/KassePayClaimAction.class.php", php_pay),
            ("lib/action/KassePayInvoiceAction.class.php", php_pay_inv),
            ("lib/action/KasseExportAction.class.php", php_export),
            ("lib/acp/page/KasseDebugPage.class.php", php_acp_debug),
            ("lib/acp/page/KasseCategoryListPage.class.php", php_acp_cat_list),
            ("lib/acp/form/KasseCategoryAddForm.class.php", php_acp_cat_add),
            ("lib/acp/page/KasseAccountListPage.class.php", php_acp_acc_list),
            ("lib/acp/form/KasseAccountAddForm.class.php", php_acp_acc_add),
            ("lib/acp/page/KasseUserFeeListPage.class.php", php_acp_mem_list),
        ]
        for name, content in file_map:
            data = content.encode('utf-8')
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    f_data = files_io.getvalue()

    tpl_io = io.BytesIO()
    with tarfile.open(fileobj=tpl_io, mode='w') as tar:
        tpl_map = [
            ("kasseOverview.tpl", tpl_overview),
            ("kasseClaim.tpl", tpl_claim),
            ("kasseAdd.tpl", tpl_add),
            ("kasseInvoice.tpl", tpl_inv),
            ("kasseFee.tpl", tpl_fee),
            ("kasseUserFee.tpl", tpl_user_fee),
            ("kasseAudit.tpl", tpl_audit),
            ("kasseLog.tpl", tpl_log),
            ("kasseMyHistory.tpl", tpl_hist),
            ("kasseAdminClaims.tpl", tpl_admin),
            ("kasseMembership.tpl", tpl_mem),
            ("kasseClaimReject.tpl", tpl_reject),
            ("kasseImport.tpl", tpl_import),
            ("kasseInvoicePrint.tpl", tpl_print),
        ]
        for name, content in tpl_map:
            data = content.encode('utf-8')
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    t_data = tpl_io.getvalue()

    acp_io = io.BytesIO()
    with tarfile.open(fileobj=acp_io, mode='w') as tar:
        acp_tpl_map = [
            ("kasseACPStatus.tpl", tpl_acp_status),
            ("kasseCategoryList.tpl", tpl_acp_cat_list),
            ("kasseCategoryAdd.tpl", tpl_acp_cat_add),
            ("kasseProjectList.tpl", tpl_acp_proj_list),
            ("kasseProjectAdd.tpl", tpl_acp_proj_add),
            ("kasseAccountList.tpl", tpl_acp_acc_list),
            ("kasseAccountAdd.tpl", tpl_acp_acc_add),
            ("kasseUserFeeList.tpl", tpl_acp_mem_list),
        ]
        for name, content in acp_tpl_map:
            data = content.encode('utf-8')
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    a_data = acp_io.getvalue()

    output_path = os.path.join(desktop, "de.wildesgebilde.kasse.tar")
    with tarfile.open(output_path, "w") as tar:
        xml_map = [
            ("package.xml", package_xml),
            ("install.sql", install_sql),
            ("acpMenu.xml", acp_menu),
            ("userGroupOption.xml", ug_xml),
            ("language/de.xml", lang_xml),
            ("page.xml", page_xml),
            ("menuItem.xml", menu_xml),
            ("option.xml", option_xml),
            ("userNotificationEvent.xml", notify_xml),
            ("eventListener.xml", evt_xml),
            ("templateListener.xml", tpl_lst_xml),
            ("objectType.xml", object_type_xml),
        ]
        for name, content in xml_map:
            data = content.encode('utf-8')
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        info = tarfile.TarInfo(name="files.tar")
        info.size = len(f_data)
        tar.addfile(info, io.BytesIO(f_data))

        info = tarfile.TarInfo(name="templates.tar")
        info.size = len(t_data)
        tar.addfile(info, io.BytesIO(t_data))

        info = tarfile.TarInfo(name="acpTemplates.tar")
        info.size = len(a_data)
        tar.addfile(info, io.BytesIO(a_data))

    print("✅ V205 COMPLETE. Package written to:", output_path)
except Exception as exc:
    print("ERROR:", exc)
